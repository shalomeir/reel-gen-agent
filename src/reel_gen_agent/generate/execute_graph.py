"""execute 페이즈 LangGraph. ReelProfile -> 영상 + RunManifest + 결과물([workflows.md]).

흐름: load -> production_plan -> stills -> materials -> assemble -> verify -> describe ->
evaluate -> report. verify는 하드 게이트다: 교정 가능한 conformance fail(이번 범위는
loudness)이면 교정 목표를 실어 assemble로 되돌려 재믹스하고(최대 3회), 통과하거나 소진하면
describe로 진행한다([repair.py]). 각 노드는 공유 상태(ExecState)를 읽고 부분 업데이트를
돌려주며, Tracer가 노드 span을 로컬 trace(+옵션 Langfuse)에 남긴다([trace.py]).

plan 산출물(캐릭터·제품)은 plan/에서 읽고, execute 생성물(앵커 스틸·클립·오디오)은 execute/
하위에 만들며, 결과물 3종(final/report/upload)+run.json은 run 루트에 떨어뜨린다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict

from ..analysis.loudness import measure_loudness
from ..analysis.rubric import evaluate_video
from .assemble import assemble
from .conformance import ConformanceConfig, verify_conformance
from .describe import build_upload_kit, render_upload_md
from .materials import (
    build_bgm_track,
    build_sfx_track,
    build_visuals,
    build_voice_track,
)
from .production_plan import resolve_plan
from .repair import (
    GENERATED_LUFS_MAX,
    GENERATED_LUFS_MIN,
    plan_repair,
    unresolved_fails,
)
from .report import build_final_report, render_report_md
from .run_context import new_manifest, output_dir_for, plan_dir_for
from .schema import Materials, NodeRun, ReelProfile
from .stills import ensure_panel_stills


class ExecState(TypedDict, total=False):
    profile_path: str
    use_vlm: bool
    tracer: Any
    profile: Any
    plan: Any
    manifest: Any
    out_dir: Any
    plan_dir: Any
    exec_dir: Any
    visuals: Any  # VisualMaterials(영상 클립+자막+total_dur), 병렬 오디오가 공유
    voice_audio: Any
    bgm_audio: Any
    bgm_gain: Any
    sfx_audio: Any
    sfx_starts: Any
    final_video: str
    conf_dump: dict
    rubric_dump: dict
    repair_attempts: int  # verify fail로 assemble을 되돌린 횟수(loudness 교정)
    loudness_target: float  # assemble에 주입할 loudnorm 교정 목표(없으면 기본 규칙)
    repair_route: str  # verify 조건 엣지가 읽을 다음 노드("assemble" | "describe")
    unresolved: list  # 진행 시점에 남은 fail 코드(증거 기록용)


def _resolve_asset(image: str | None, base_dir: Path) -> str | None:
    """ReelProfile에 상대 파일명으로 적힌 에셋 이미지를 절대 경로로 푼다."""
    if not image:
        return None
    p = Path(image)
    if not p.is_absolute():
        p = base_dir / p
    return str(p) if p.exists() else None


def _load_node(state: ExecState) -> dict:
    pp = state["profile_path"]
    with state["tracer"].node("load"):
        profile = ReelProfile.model_validate_json(Path(pp).read_text(encoding="utf-8"))
        out_dir = output_dir_for(pp)
        return {
            "profile": profile,
            "out_dir": out_dir,
            "plan_dir": plan_dir_for(pp),
            "exec_dir": out_dir / "execute",
            "manifest": new_manifest(pp, profile),
        }


def _plan_node(state: ExecState) -> dict:
    with state["tracer"].node("production_plan"):
        plan = resolve_plan(state["profile"], env=dict(os.environ))
        state["manifest"].production_plan = plan
        state["manifest"].nodes.append(NodeRun(name="production_plan"))
        return {"plan": plan}


def _reuse_key_visual_as_anchor(profile, plan, base_dir: Path) -> None:
    """대표 key_visual을 중간 세그먼트 앵커 스틸로 재활용한다(그 세그먼트 시작 프레임).

    key_visual은 중간 패널의 대표 순간으로 그려졌으므로, 그 세그먼트의 앵커 스틸로 그대로 쓰면
    자연스럽다(Veo 시작 프레임/ken_burns 폴백이 이걸 쓴다). 이미 스틸이 있으면 건드리지 않는다.
    """
    kv = _resolve_asset(profile.asset_bible.key_visual, base_dir)
    segments = plan.segments or []
    if not kv or not segments:
        return
    mid_seg = segments[len(segments) // 2]
    if not mid_seg:
        return
    panel = profile.storyboard.panels[mid_seg[0]]
    if not panel.still_image:
        panel.still_image = kv


def _stills_node(state: ExecState) -> dict:
    profile, plan = state["profile"], state["plan"]
    anchor_indices = {seg[0] for seg in plan.segments if seg}
    base_dir = state["plan_dir"].resolve()  # 캐릭터·제품·키비주얼 에셋은 plan/ 안에 있다
    # 대표 key_visual을 중간 세그먼트 앵커로 먼저 재활용(그만큼 새로 생성할 스틸이 준다).
    _reuse_key_visual_as_anchor(profile, plan, base_dir)
    if not any(not p.still_image for p in profile.storyboard.panels if p.index in anchor_indices):
        return {}
    with state["tracer"].node("stills"):
        char_img = _resolve_asset(profile.asset_bible.character.key_shot_image, base_dir)
        prod_img = _resolve_asset(profile.asset_bible.product.hero_image, base_dir)
        client = None
        if os.environ.get("REEL_STILLS", "gen").lower() != "off":
            try:
                from .image_client import NanoBananaImageClient

                client = NanoBananaImageClient()
            except Exception:
                client = None
        kv_img = _resolve_asset(profile.asset_bible.key_visual, base_dir)
        filled = ensure_panel_stills(
            profile,
            str(state["exec_dir"]),
            client,
            char_img,
            prod_img,
            anchor_indices=anchor_indices,
            key_visual=kv_img,
        )
        state["manifest"].nodes.append(NodeRun(name="stills", artifacts=[]))
        if filled == 0:
            raise ValueError("stills: 채울 수 있는 앵커 스틸이 없다(에셋 이미지 확인).")
        # 스틸 경로를 plan ReelProfile에 되써 재실행(execute만) 저비용화.
        Path(state["profile_path"]).write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return {}


def _visuals_node(state: ExecState) -> dict:
    """순차 영상 생성(key image -> video, 컷별로 이전 컷 연결). 씬 오디오도 여기서 함께 난다.

    이후 voice/bgm/sfx 3개 오디오 노드가 이 total_dur를 공유해 병렬로 트랙을 만든다.
    """
    with state["tracer"].node("visuals") as span:
        profile = state["profile"]
        base_dir = state["plan_dir"].resolve()
        char_img = _resolve_asset(profile.asset_bible.character.key_shot_image, base_dir)
        prod_img = _resolve_asset(profile.asset_bible.product.hero_image, base_dir)
        # 영상 모델이 세그먼트에 실패하면 그 컷들만 개별 스틸을 생성해 몽타주를 유지한다(비용 0).
        img_client = None
        if os.environ.get("REEL_STILLS", "gen").lower() != "off":
            try:
                from .image_client import NanoBananaImageClient

                img_client = NanoBananaImageClient()
            except Exception:
                img_client = None
        kv_img = _resolve_asset(profile.asset_bible.key_visual, base_dir)
        visuals = build_visuals(
            profile,
            state["plan"],
            str(state["exec_dir"]),
            image_client=img_client,
            character_image=char_img,
            product_image=prod_img,
            key_visual=kv_img,
        )
        # 영상 모델에 보낸 세그먼트 프롬프트를 매니페스트(리포트 "노드별 프롬프트")와 trace에 남긴다.
        video_prompt = "\n\n".join(visuals.prompts) or None
        if video_prompt:
            span.set(output=video_prompt)
        state["manifest"].nodes.append(
            NodeRun(name="visuals", artifacts=visuals.shot_clips, prompt=video_prompt)
        )
        return {"visuals": visuals}


def _voice_node(state: ExecState) -> dict:
    """나레이션 voice 트랙(delivery=voiceover일 때만). 영상 모델이 발화를 품는 integrated면 no-op.

    병렬 노드라 공유 manifest는 건드리지 않는다(레이스 방지). 노드 기록은 fan-in(assemble)에서 한다.
    """
    with state["tracer"].node("voice"):
        voice = build_voice_track(
            state["profile"], str(state["exec_dir"]), state["visuals"].total_dur
        )
        return {"voice_audio": voice}


def _bgm_node(state: ExecState) -> dict:
    """BGM 트랙(거의 항상, plan.bgm!=none). 영상 생성과 무관하게 병렬로 만든다."""
    with state["tracer"].node("bgm"):
        bgm, gain = build_bgm_track(
            state["profile"], state["plan"], str(state["exec_dir"]), state["visuals"].total_dur
        )
        return {"bgm_audio": bgm, "bgm_gain": gain}


def _sfx_node(state: ExecState) -> dict:
    """프로덕션 효과음 트랙(plan.sfx일 때만, 보수적). 씬 자연음은 영상 모델 몫이라 여기 없다."""
    with state["tracer"].node("sfx"):
        sfx_audio, sfx_starts = build_sfx_track(
            state["profile"], state["plan"], str(state["exec_dir"])
        )
        return {"sfx_audio": sfx_audio, "sfx_starts": sfx_starts}


def _assemble_node(state: ExecState) -> dict:
    """visuals + 병렬 오디오 3종을 Materials로 합쳐 최종 mp4를 만든다(fan-in).

    병렬 오디오 노드는 manifest를 안 건드리므로, 여기서 voice/bgm/sfx/assemble 기록을 모아 남긴다.
    """
    with state["tracer"].node("assemble"):
        v = state["visuals"]
        for name in ("voice", "bgm", "sfx"):
            state["manifest"].nodes.append(NodeRun(name=name))
        materials = Materials(
            shot_clips=v.shot_clips,
            subtitle_pngs=v.subtitle_pngs,
            subtitle_spans=v.subtitle_spans,
            bgm_audio=state.get("bgm_audio"),
            voice_audio=state.get("voice_audio"),
            sfx_audio=state.get("sfx_audio") or [],
            sfx_starts=state.get("sfx_starts") or [],
            native_audio=v.native_audio,
            bgm_gain=state.get("bgm_gain"),
        )
        final_video = str(state["out_dir"] / "final.mp4")
        # loudness_target이 있으면(verify repair 교정) 그 목표로 재믹스한다.
        assemble(
            materials,
            state["profile"].meta,
            final_video,
            loudness_target=state.get("loudness_target"),
        )
        m = state["manifest"]
        m.final_video = final_video
        m.panel_segments = materials.shot_clips
        m.nodes.append(NodeRun(name="assemble", artifacts=[final_video]))
        return {"final_video": final_video}


def _verify_node(state: ExecState) -> dict:
    """conformance로 결과물을 검증하고, 교정 가능한 fail이면 assemble로 되돌린다(하드 게이트).

    생성물에는 기본보다 타이트한 loudness 밴드를 걸어 게이트를 살린다. loudness fail이면
    라우드니스를 직접 재서(analysis.loudness) 교정 목표를 뽑고, assemble을 재믹스시킨다.
    최대 3회. 소진하거나 교정 불가면 소프트 통과로 describe로 가되 미해결 fail을 기록한다.
    """
    attempts = state.get("repair_attempts", 0)
    with state["tracer"].node("verify", attempt=attempts):
        config = ConformanceConfig(lufs_min=GENERATED_LUFS_MIN, lufs_max=GENERATED_LUFS_MAX)
        conf = verify_conformance(
            state["final_video"], use_vlm=state.get("use_vlm", True), config=config
        )
        state["manifest"].nodes.append(NodeRun(name="verify"))
        loud = measure_loudness(state["final_video"])
        action = plan_repair(conf, config, loud.lufs if loud.measured else None, attempts)
        if action is not None:
            return {
                "conf_dump": conf.model_dump(),
                "loudness_target": action.loudness_target,
                "repair_attempts": attempts + 1,
                "repair_route": action.target,
            }
        return {
            "conf_dump": conf.model_dump(),
            "repair_route": "describe",
            "unresolved": unresolved_fails(conf),
        }


def _describe_node(state: ExecState) -> dict:
    with state["tracer"].node("describe"):
        kit = build_upload_kit(state["profile"])
        out = str(state["out_dir"] / "upload.md")
        render_upload_md(kit, out)
        state["manifest"].nodes.append(NodeRun(name="describe", artifacts=[out]))
        return {}


def _evaluate_node(state: ExecState) -> dict:
    with state["tracer"].node("evaluate"):
        rubric_dump: dict = {}
        if state.get("use_vlm", True):
            rubric_dump = evaluate_video(state["final_video"]).model_dump()
        state["manifest"].nodes.append(NodeRun(name="evaluate"))
        return {"rubric_dump": rubric_dump}


def _report_node(state: ExecState) -> dict:
    with state["tracer"].node("report"):
        out_dir = state["out_dir"]
        m = state["manifest"]
        report = build_final_report(
            out_dir.name,
            state["profile"],
            m,
            state["conf_dump"],
            state.get("rubric_dump", {}),
            repair={
                "attempts": state.get("repair_attempts", 0),
                "unresolved": state.get("unresolved", []),
            },
        )
        out = str(out_dir / "report.md")
        render_report_md(report, out)
        m.nodes.append(NodeRun(name="report", artifacts=[out]))
        (out_dir / "run.json").write_text(m.model_dump_json(indent=2), encoding="utf-8")
        return {}


def build_execute_graph():
    """execute 페이즈 StateGraph를 컴파일한다."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(ExecState)
    for name, fn in [
        ("load", _load_node),
        ("production_plan", _plan_node),
        ("stills", _stills_node),
        ("visuals", _visuals_node),
        ("voice", _voice_node),
        ("bgm", _bgm_node),
        ("sfx", _sfx_node),
        ("assemble", _assemble_node),
        ("verify", _verify_node),
        ("describe", _describe_node),
        ("evaluate", _evaluate_node),
        ("report", _report_node),
    ]:
        g.add_node(name, fn)
    # load -> plan -> stills -> visuals(순차 영상) -> [voice, bgm, sfx 병렬] -> assemble -> ...
    g.add_edge(START, "load")
    g.add_edge("load", "production_plan")
    g.add_edge("production_plan", "stills")
    g.add_edge("stills", "visuals")
    # fan-out: 오디오 3종을 병렬로. 각 노드는 plan 플래그로 self-gate(voiceover만 voice, plan.sfx만 sfx).
    for audio in ("voice", "bgm", "sfx"):
        g.add_edge("visuals", audio)
        g.add_edge(audio, "assemble")  # fan-in: assemble은 셋을 모두 기다린다.
    g.add_edge("assemble", "verify")
    # verify 하드 게이트: 교정 가능한 fail이면 assemble로 되돌려 재믹스(최대 3회), 아니면 describe.
    g.add_conditional_edges(
        "verify",
        lambda s: s.get("repair_route", "describe"),
        {"assemble": "assemble", "describe": "describe"},
    )
    for a, b in [("describe", "evaluate"), ("evaluate", "report")]:
        g.add_edge(a, b)
    g.add_edge("report", END)
    return g.compile()
