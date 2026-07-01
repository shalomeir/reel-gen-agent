"""plan 페이즈 LangGraph. 노드/조건부 엣지로 ReelProfile을 만든다([workflows.md]).

흐름: intake -> reference_seed -> product -> character -> environment -> hook <-> storyboard
(핑퐁 루프) -> narration -> music -> write. music은 확정 훅·스토리·나레이션을 보고 정하도록
마지막에 둔다. 각 노드는 공유 상태(PlanState)를 읽고 부분
업데이트를 돌려주며, Tracer가 노드 span을 로컬 trace(+옵션 Langfuse)에 남긴다.

hook <-> storyboard 핑퐁: storyboard 노드가 주어진 hook을 전체 스토리에 녹여보고 안 맞으면
hook_fits=False + 힌트를 낸다. 조건부 엣지가 그 힌트로 hook 노드를 다시 부르고(최대
MAX_HOOK_ATTEMPTS회) storyboard를 재실행한다. LLM(text_client)이 없으면 스토리보드는
결정론 템플릿으로 폴백하고 핑퐁 없이 통과한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from .asset_bible import build_character_asset, build_key_visual, build_product_asset
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
    AssetBible,
    CharacterProfile,
    HookRequest,
    InputMeta,
    MusicSpec,
    NarrationSpec,
    ProductProfile,
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
    # 입력으로 받은 인물·제품 이미지의 로컬 경로(있으면 에셋 생성의 참조로 쓴다).
    character_image: str
    product_image: str
    # 입력으로 받은 제품 URL(있으면 판매 페이지를 스크래핑해 카탈로그 근거로 쓴다).
    product_url: str
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
    ref_voice_tone: str
    ref_voice_pace: str
    cut_count: int
    provenance: Any
    style_feedback: str
    hook_feedback: str
    hook_attempts: int
    storyboard: Any
    narration: Any
    narrative_arc: list
    character_profile: Any  # 캐릭터 노드가 생성한 에셋(이미지)
    product_profile: Any  # 제품 노드가 생성한 에셋(이미지)
    profile_path: str


def _intake_node(state: PlanState) -> dict:
    from .schema import ProductSpec

    with state["tracer"].node("intake"):
        result = intake(state["raw"])
        if result.objective is None:
            raise ValueError("objective(영상 목적)는 필수다. 입력이 비었다.")
        # 제품 소스가 로컬 이미지/URL이면 그건 참조일 뿐 이름이 아니다. 그 경우 이름은 비워
        # 두고(=product), 제품 노드의 LLM이 브리프에서 실제 제품명을 추론하게 한다.
        product_name = result.product.source or "product"
        product_url = ""
        if (result.product.source or "").startswith(("http://", "https://")):
            product_url = result.product.source or ""
            product_name = "product"
        elif result.product_image:
            product_name = "product"
        return {
            "objective": result.objective,
            "product": ProductSpec(name=product_name),
            "character_image": result.character_image or "",
            "product_image": result.product_image or "",
            "product_url": product_url,
            "meta": InputMeta(),
            "style": StyleDimensions(),
            "music": MusicSpec(),
            "delivery": "voiceover",
            "cut_count": 0,
            "hook_attempts": 0,
            "hook_feedback": "",
            "ref_subject": None,
            "ref_hook": None,
            "ref_voice_tone": "",
            "ref_voice_pace": "",
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
            "ref_voice_tone": seed.voice_tone or "",
            "ref_voice_pace": seed.voice_pace or "",
        }


def _plan_asset_dir(state: PlanState) -> str:
    """이 run의 plan/ 폴더(에셋 이미지 저장 위치). 노드 어디서든 run_id로 해소한다."""
    return str(create_run_dir(state["outputs_root"], state["tracer"].run_id) / "plan")


def _product_node(state: PlanState) -> dict:
    """제품 분석 + 제품 에셋 생성. 이 단계에서 제품 히어로·패키지 이미지까지 만든다(노드에서 처리).

    제품 URL이 있으면 판매 페이지를 스크래핑해 본문·제품 사진 다수를 근거로 모으고(백업 자료),
    그 사진들을 VLM으로 함께 분석해 실제 제품의 특징을 반영한 ProductSpec을 뽑는다(product_source).
    스크래핑/분석이 안 되면 텍스트 브리프 기반 derive_product로 폴백한다. 실제 제품 사진은 히어로/
    패키지 렌더의 참조로도 쓴다. 이 노드 산출물(스펙+사진)이 훅·스토리보드로도 흘러 앵커가 된다.
    """
    from .product_source import collect_materials, extract_product

    with state["tracer"].node("product"):
        goal = state["objective"].goal
        plan_dir = _plan_asset_dir(state)
        url = (state.get("product_url") or "").strip()

        materials = collect_materials(url, plan_dir) if url else None
        # 참조 이미지: 스크래핑한 실제 제품 사진(상위 2장) + 사용자가 직접 준 로컬 제품 이미지.
        refs = list(materials.image_paths[:2]) if materials else []
        local_img = state.get("product_image")
        if local_img:
            refs.append(local_img)

        product = None
        if materials is not None:
            product = extract_product(materials, fallback_name=state["product"].name)
        if product is None:  # 스크래핑/분석 실패 -> 텍스트 경로(근거 있으면 web_context로 전달)
            product = derive_product(
                state["product"].name, goal, state.get("ref_product"),
                state.get("text_client"),
                web_context=(materials.web_context if materials else ""),
            )

        profile = build_product_asset(
            product, state.get("image_client"), plan_dir,
            palette=state["style"].palette, refs=refs,
        )
        return {"product": product, "product_profile": profile}


def _character_node(state: PlanState) -> dict:
    """캐릭터 도출 + 캐릭터 레퍼런스 시트 생성. 이 단계에서 인물 이미지까지 만든다(노드에서 처리)."""
    with state["tracer"].node("character"):
        character = derive_character(
            state["objective"].goal, state["product"], state.get("ref_subject"),
            state.get("text_client"),
        )
        profile = build_character_asset(
            character, state.get("image_client"), _plan_asset_dir(state),
            palette=state["style"].palette,
            refs=[r for r in [state.get("character_image")] if r],
        )
        return {"character": character, "character_profile": profile}


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
                pacing=state["style"].pacing,
                # music은 plan 마지막 노드다. 핑퐁으로 확정된 최종 훅과 스토리보드·아크·나레이션을
                # 넘겨, 장르·리듬·다이내믹스는 스토리 전개에, prominence(→BGM 볼륨)는 나레이션
                # 강도에 맞춰 LLM이 정하게 한다(하드코딩 아닌 노드별 LLM 판단).
                hook=state["style"].hook,
                storyboard=state["storyboard"],
                narrative_arc=state.get("narrative_arc"),
                narration=state["narration"],
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
                cut_count=cut_n, text_client=text_client,
                style_feedback=state.get("style_feedback", ""), **common,
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
    # voice의 '결'은 레퍼런스 관측(tone/pace)을 우선 싣는다. 없으면 캐릭터 페르소나 기본 연기.
    narration = NarrationSpec(
        delivery=state["delivery"],
        voice=VoiceSpec(
            from_character=True,
            type=voice_persona(state["character"]),
            tone=state.get("ref_voice_tone") or None,
            pace=state.get("ref_voice_pace") or None,
        ),
    )
    if state.get("text_client") is not None:
        with state["tracer"].node("narration"):
            from .planning_nodes import narration_lines

            narration.lines = narration_lines(
                state["text_client"], state["product"], state["style"], state["meta"],
                [p.beat or "" for p in sb.panels], character=state["character"],
                delivery_tone=state.get("ref_voice_tone") or None,
                delivery_pace=state.get("ref_voice_pace") or None,
            )
    arc = [p.beat for p in sb.panels if p.beat]
    return {"narration": narration, "narrative_arc": arc}


def _write_node(state: PlanState) -> dict:
    with state["tracer"].node("write_profile"):
        run_id = state["tracer"].run_id
        plan_dir = create_run_dir(state["outputs_root"], run_id) / "plan"
        # AssetBible은 각 노드가 만든 캐릭터·제품 에셋 + 환경 스펙을 모아 조립한다(통합 노드 없음).
        asset_bible = AssetBible(
            character=state.get("character_profile") or CharacterProfile(name=state["character"].name),
            product=state.get("product_profile") or ProductProfile(name=state["product"].name),
            environment=state["environment"],
        )
        profile = assemble_profile(
            {
                "objective": state["objective"], "product": state["product"],
                "meta": state["meta"], "character": state["character"], "style": state["style"],
                "narrative_arc": state["narrative_arc"], "asset_bible": asset_bible,
                "storyboard": state["storyboard"], "narration": state["narration"],
                "music": state["music"], "provenance": state["provenance"],
            }
        )
        # plan 확정: 캐릭터·제품·환경 에셋 + 프로필을 합쳐 영상 대표 키 비주얼 한 장을 만든다.
        # asset_bible은 profile이 참조하는 같은 객체라, 여기 key_visual을 심으면 프로필에도 반영된다.
        char_ref = str(plan_dir / asset_bible.character.key_shot_image) if asset_bible.character.key_shot_image else None
        prod_ref = str(plan_dir / asset_bible.product.hero_image) if asset_bible.product.hero_image else None
        asset_bible.key_visual = build_key_visual(
            profile, state.get("image_client"), str(plan_dir), char_ref, prod_ref
        )
        path = write_profile(profile, plan_dir, run_id)
        return {"profile_path": str(path)}


def build_plan_graph():
    """plan 페이즈 StateGraph를 컴파일한다."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(PlanState)
    # 통합 assets 노드 없음: 캐릭터·제품 에셋은 각 노드가 그 단계에서 생성한다.
    for name, fn in [
        ("intake", _intake_node), ("reference_seed", _reference_node),
        ("product", _product_node),
        ("character", _character_node), ("environment", _environment_node),
        ("music", _music_node), ("hook", _hook_node), ("storyboard", _storyboard_node),
        ("narration", _narration_node), ("write_profile", _write_node),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_edge("intake", "reference_seed")
    g.add_edge("reference_seed", "product")
    g.add_edge("product", "character")
    g.add_edge("character", "environment")
    g.add_edge("environment", "hook")
    g.add_edge("hook", "storyboard")
    g.add_conditional_edges(
        "storyboard", _route_after_storyboard, {"hook": "hook", "narration": "narration"}
    )
    # music은 plan의 마지막 노드다: 확정 훅·스토리·나레이션을 보고 음악을 정한 뒤 write로.
    g.add_edge("narration", "music")
    g.add_edge("music", "write_profile")
    g.add_edge("write_profile", END)
    return g.compile()
