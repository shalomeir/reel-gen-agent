"""plan 페이즈 LangGraph. 노드/조건부 엣지로 ReelProfile을 만든다([workflows.md]).

흐름: intake -> reference_seed -> character -> environment -> music -> hook <-> storyboard
(핑퐁 루프) -> narration -> assets -> write. 각 노드는 공유 상태(PlanState)를 읽고 부분
업데이트를 돌려주며, Tracer가 노드 span을 로컬 trace(+옵션 Langfuse)에 남긴다.

hook <-> storyboard 핑퐁: storyboard 노드가 주어진 hook을 전체 스토리에 녹여보고 안 맞으면
hook_fits=False + 힌트를 낸다. 조건부 엣지가 그 힌트로 hook 노드를 다시 부르고(최대
MAX_HOOK_ATTEMPTS회) storyboard를 재실행한다. LLM(text_client)이 없으면 스토리보드는
결정론 템플릿으로 폴백하고 핑퐁 없이 통과한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from .asset_bible import build_asset_bible
from .character import character_brief, derive_character, voice_persona
from .environment import derive_environment
from .hook import generate_hooks
from .intake import intake
from .music import derive_music
from .product import derive_product
from .profile_assembly import assemble_profile, write_profile
from .reference_seed import seed_from_reference
from .run_paths import create_run_dir
from .schema import (
    HookRequest,
    InputMeta,
    MusicSpec,
    NarrationSpec,
    Provenance,
    StyleDimensions,
    VoiceSpec,
)
from .storyboard import build_storyboard, storyboard_from_panels
from .storyboard_planner import plan_story_panels

MAX_HOOK_ATTEMPTS = 2


class PlanState(TypedDict, total=False):
    raw: str
    outputs_root: str
    text_client: Any
    image_client: Any
    tracer: Any
    # 파생 컨텍스트(노드가 채운다)
    objective: Any
    product: Any
    meta: Any
    style: Any
    music: Any
    character: Any
    environment: Any
    delivery: str
    ref_subject: Any
    ref_hook: Any
    ref_product: Any
    cut_count: int
    provenance: Any
    hook_feedback: str
    hook_attempts: int
    storyboard: Any
    narration: Any
    narrative_arc: list
    asset_bible: Any
    profile_path: str


def _intake_node(state: PlanState) -> dict:
    from .schema import ProductSpec

    with state["tracer"].node("intake"):
        result = intake(state["raw"])
        if result.objective is None:
            raise ValueError("objective(영상 목적)는 필수다. 입력이 비었다.")
        return {
            "objective": result.objective,
            "product": ProductSpec(name=(result.product.source or "product")),
            "meta": InputMeta(),
            "style": StyleDimensions(),
            "music": MusicSpec(),
            "delivery": "voiceover",
            "cut_count": 0,
            "hook_attempts": 0,
            "hook_feedback": "",
            "ref_subject": None,
            "ref_hook": None,
            "provenance": Provenance(
                style_source="reference" if result.reference_ref else "llm",
                reference_ref=result.reference_ref,
            ),
        }


def _reference_node(state: PlanState) -> dict:
    ref = state["provenance"].reference_ref
    if not (ref and Path(ref).exists()):
        return {}
    with state["tracer"].node("reference_seed", ref=ref):
        try:
            seed = seed_from_reference(ref, use_gemini=state.get("text_client") is not None)
        except Exception:
            return {}  # 시딩 실패해도 기본값으로 계속
        return {
            "meta": seed.meta,
            "style": seed.style,
            "music": seed.music,
            "cut_count": seed.cut_count or 0,
            "delivery": seed.delivery,
            "ref_subject": seed.subject,
            "ref_hook": seed.style.hook,
            "ref_product": seed.product,
        }


def _product_node(state: PlanState) -> dict:
    """제품 분석: 이름만 들고온 product를 카테고리·USP·용기·행동으로 채운다(레퍼런스 힌트 반영)."""
    with state["tracer"].node("product"):
        return {
            "product": derive_product(
                state["product"].name, state["objective"].goal, state.get("ref_product"),
                state.get("text_client"),
            )
        }


def _character_node(state: PlanState) -> dict:
    with state["tracer"].node("character"):
        return {
            "character": derive_character(
                state["objective"].goal, state["product"], state.get("ref_subject"),
                state.get("text_client"),
            )
        }


def _environment_node(state: PlanState) -> dict:
    with state["tracer"].node("environment"):
        return {
            "environment": derive_environment(
                state["objective"].goal, state["product"], state["character"],
                state.get("text_client"),
            )
        }


def _music_node(state: PlanState) -> dict:
    with state["tracer"].node("music"):
        return {
            "music": derive_music(
                state["objective"].goal, state["product"], state["style"].tone,
                state["music"], state.get("text_client"), character=state["character"],
            )
        }


def _hook_node(state: PlanState) -> dict:
    """훅을 생성/개선한다. hook_feedback이 있으면(스토리보드가 반려) 그 힌트를 반영해 재생성."""
    text_client = state.get("text_client")
    style = state["style"]
    ref_hook = state.get("ref_hook")
    attempts = state.get("hook_attempts", 0) + 1
    if text_client is None:
        return {"hook_attempts": attempts}  # LLM 없으면 레퍼런스 훅(seed) 유지
    with state["tracer"].node("hook", attempt=attempts, feedback=state.get("hook_feedback", "")):
        goal = state["objective"].goal
        feedback = state.get("hook_feedback", "")
        brief = f"{goal}\nStoryboard feedback on the hook: {feedback}" if feedback else goal
        try:
            hooks = generate_hooks(
                HookRequest(
                    product=state["product"], tone=style.tone,
                    character=character_brief(state["character"]),
                    language=state["meta"].language, duration_sec=state["meta"].duration_sec,
                    count=2,
                ),
                text_client,
                brief=brief,
            )
        except Exception:
            return {"hook_attempts": attempts}
        if not hooks.candidates:
            return {"hook_attempts": attempts}
        chosen = hooks.candidates[0]
        if ref_hook is not None:
            # 레퍼런스의 첫 3초 비주얼·문구·윈도를 얹는다(유형은 LLM 선택 유지).
            if ref_hook.visual_direction:
                chosen.visual_direction = ref_hook.visual_direction
            if ref_hook.headline:
                chosen.headline = ref_hook.headline
            if ref_hook.bottom_caption:
                chosen.bottom_caption = ref_hook.bottom_caption
            chosen.window_sec = ref_hook.window_sec
        style.hook = chosen
        return {"style": style, "hook_attempts": attempts}


def _storyboard_node(state: PlanState) -> dict:
    text_client = state.get("text_client")
    common = dict(
        meta=state["meta"], style=state["style"], product=state["product"],
        character=state["character"], environment=state["environment"],
    )
    with state["tracer"].node("storyboard", attempt=state.get("hook_attempts", 0)):
        n = state.get("cut_count") or None
        if text_client is None:
            sb = build_storyboard(cut_count=n, **common)
            return {"storyboard": sb, "hook_feedback": ""}
        from .storyboard import _panel_count  # 컷 수 결정 재사용

        cut_n = _panel_count(state["meta"], state["style"], n)
        try:
            plan = plan_story_panels(
                objective_goal=state["objective"].goal, hook=state["style"].hook,
                cut_count=cut_n, text_client=text_client, **common,
            )
        except Exception:
            sb = build_storyboard(cut_count=n, **common)
            return {"storyboard": sb, "hook_feedback": ""}
        sb = storyboard_from_panels(plan.panels, **common)
        return {"storyboard": sb, "hook_feedback": ("" if plan.hook_fits else plan.hook_feedback)}


def _route_after_storyboard(state: PlanState) -> str:
    """훅이 스토리에 안 맞고 재시도 여유가 있으면 hook으로 되돌아가 핑퐁한다."""
    if state.get("text_client") is None:
        return "narration"
    if state.get("hook_feedback") and state.get("hook_attempts", 0) < MAX_HOOK_ATTEMPTS:
        return "hook"
    return "narration"


def _narration_node(state: PlanState) -> dict:
    sb = state["storyboard"]
    narration = NarrationSpec(
        delivery=state["delivery"],
        voice=VoiceSpec(from_character=True, type=voice_persona(state["character"])),
    )
    if state.get("text_client") is not None:
        with state["tracer"].node("narration"):
            from .planning_nodes import narration_lines

            narration.lines = narration_lines(
                state["text_client"], state["product"], state["style"], state["meta"],
                [p.beat or "" for p in sb.panels], character=state["character"],
            )
    arc = [p.beat for p in sb.panels if p.beat]
    return {"narration": narration, "narrative_arc": arc}


def _assets_node(state: PlanState) -> dict:
    with state["tracer"].node("assets"):
        run_id = state["tracer"].run_id
        out_dir = create_run_dir(state["outputs_root"], run_id)
        plan_dir = out_dir / "plan"
        plan_dir.mkdir(parents=True, exist_ok=True)
        asset_bible = build_asset_bible(
            state["character"], state["product"], state["environment"],
            state.get("image_client"), str(plan_dir), palette=state["style"].palette,
        )
        return {"asset_bible": asset_bible}


def _write_node(state: PlanState) -> dict:
    with state["tracer"].node("write_profile"):
        run_id = state["tracer"].run_id
        plan_dir = create_run_dir(state["outputs_root"], run_id) / "plan"
        profile = assemble_profile(
            {
                "objective": state["objective"], "product": state["product"],
                "meta": state["meta"], "character": state["character"], "style": state["style"],
                "narrative_arc": state["narrative_arc"], "asset_bible": state["asset_bible"],
                "storyboard": state["storyboard"], "narration": state["narration"],
                "music": state["music"], "provenance": state["provenance"],
            }
        )
        path = write_profile(profile, plan_dir, run_id)
        return {"profile_path": str(path)}


def build_plan_graph():
    """plan 페이즈 StateGraph를 컴파일한다."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(PlanState)
    for name, fn in [
        ("intake", _intake_node), ("reference_seed", _reference_node),
        ("product", _product_node),
        ("character", _character_node), ("environment", _environment_node),
        ("music", _music_node), ("hook", _hook_node), ("storyboard", _storyboard_node),
        ("narration", _narration_node), ("assets", _assets_node), ("write_profile", _write_node),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_edge("intake", "reference_seed")
    g.add_edge("reference_seed", "product")
    g.add_edge("product", "character")
    g.add_edge("character", "environment")
    g.add_edge("environment", "music")
    g.add_edge("music", "hook")
    g.add_edge("hook", "storyboard")
    g.add_conditional_edges(
        "storyboard", _route_after_storyboard, {"hook": "hook", "narration": "narration"}
    )
    g.add_edge("narration", "assets")
    g.add_edge("assets", "write_profile")
    g.add_edge("write_profile", END)
    return g.compile()
