"""execute 페이즈 LangGraph. ReelProfile -> 영상 + RunManifest + 결과물([workflows.md]).

흐름: load -> production_plan -> stills -> materials -> assemble -> verify -> describe ->
evaluate -> report. 각 노드는 공유 상태(ExecState)를 읽고 부분 업데이트를 돌려주며, Tracer가
노드 span을 로컬 trace(+옵션 Langfuse)에 남긴다([trace.py]).

plan 산출물(캐릭터·제품)은 plan/에서 읽고, execute 생성물(앵커 스틸·클립·오디오)은 execute/
하위에 만들며, 결과물 3종(final/report/upload)+run.json은 run 루트에 떨어뜨린다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict

from ..analysis.rubric import evaluate_video
from .assemble import assemble
from .conformance import verify_conformance
from .describe import build_upload_kit, render_upload_md
from .materials import build_materials
from .production_plan import resolve_plan
from .report import build_final_report, render_report_md
from .run_context import new_manifest, output_dir_for, plan_dir_for
from .schema import NodeRun, ReelProfile
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
    materials: Any
    final_video: str
    conf_dump: dict
    rubric_dump: dict


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


def _stills_node(state: ExecState) -> dict:
    profile, plan = state["profile"], state["plan"]
    anchor_indices = {seg[0] for seg in plan.segments if seg}
    if not any(
        not p.still_image for p in profile.storyboard.panels if p.index in anchor_indices
    ):
        return {}
    with state["tracer"].node("stills"):
        base_dir = state["plan_dir"].resolve()  # 캐릭터·제품 에셋은 plan/ 안에 있다
        char_img = _resolve_asset(profile.asset_bible.character.key_shot_image, base_dir)
        prod_img = _resolve_asset(profile.asset_bible.product.hero_image, base_dir)
        client = None
        if os.environ.get("REEL_STILLS", "gen").lower() != "off":
            try:
                from .image_client import NanoBananaImageClient

                client = NanoBananaImageClient()
            except Exception:
                client = None
        filled = ensure_panel_stills(
            profile, str(state["exec_dir"]), client, char_img, prod_img,
            anchor_indices=anchor_indices,
        )
        state["manifest"].nodes.append(NodeRun(name="stills", artifacts=[]))
        if filled == 0:
            raise ValueError("stills: 채울 수 있는 앵커 스틸이 없다(에셋 이미지 확인).")
        # 스틸 경로를 plan ReelProfile에 되써 재실행(execute만) 저비용화.
        Path(state["profile_path"]).write_text(
            profile.model_dump_json(indent=2), encoding="utf-8"
        )
    return {}


def _materials_node(state: ExecState) -> dict:
    with state["tracer"].node("materials"):
        materials = build_materials(state["profile"], state["plan"], str(state["exec_dir"]))
        state["manifest"].nodes.append(NodeRun(name="materials", artifacts=materials.shot_clips))
        return {"materials": materials}


def _assemble_node(state: ExecState) -> dict:
    with state["tracer"].node("assemble"):
        final_video = str(state["out_dir"] / "final.mp4")
        assemble(state["materials"], state["profile"].meta, final_video)
        m = state["manifest"]
        m.final_video = final_video
        m.panel_segments = state["materials"].shot_clips
        m.nodes.append(NodeRun(name="assemble", artifacts=[final_video]))
        return {"final_video": final_video}


def _verify_node(state: ExecState) -> dict:
    with state["tracer"].node("verify"):
        conf = verify_conformance(state["final_video"], use_vlm=state.get("use_vlm", True))
        state["manifest"].nodes.append(NodeRun(name="verify"))
        return {"conf_dump": conf.model_dump()}


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
            out_dir.name, state["profile"], m, state["conf_dump"], state.get("rubric_dump", {})
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
        ("load", _load_node), ("production_plan", _plan_node), ("stills", _stills_node),
        ("materials", _materials_node), ("assemble", _assemble_node), ("verify", _verify_node),
        ("describe", _describe_node), ("evaluate", _evaluate_node), ("report", _report_node),
    ]:
        g.add_node(name, fn)
    order = [
        "load", "production_plan", "stills", "materials", "assemble", "verify",
        "describe", "evaluate", "report",
    ]
    g.add_edge(START, order[0])
    for a, b in zip(order, order[1:], strict=False):
        g.add_edge(a, b)
    g.add_edge(order[-1], END)
    return g.compile()
