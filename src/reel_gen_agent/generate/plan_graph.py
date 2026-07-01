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
from .character import (
    character_brief,
    derive_character,
    describe_character_image,
    voice_persona,
)
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
        product_url = result.product_url or ""
        if (result.product.source or "").startswith(("http://", "https://")):
            product_url = product_url or result.product.source or ""
            product_name = "product"
        elif result.product_image and (result.product.source or "").lower().endswith(
            (".jpg", ".jpeg", ".png", ".webp")
        ):
            product_name = "product"
        return {
            "objective": result.objective,
            "product": ProductSpec(name=product_name),
            "character_image": result.character_image or "",
            "product_image": result.product_image or "",
            "product_url": product_url,
            "meta": InputMeta(language=result.language or "en"),
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
    if not ref:
        return {}
    local_ref = ref
    if ref.startswith(("http://", "https://")):
        try:
            from ..analysis.reference import _find_project_root, download_via_script

            local_ref = str(download_via_script(ref, _find_project_root()))
        except Exception as exc:
            raise RuntimeError(f"레퍼런스 영상 URL 다운로드 실패: {ref}") from exc
    if not Path(local_ref).exists():
        return {}
    with state["tracer"].node("reference_seed", ref=local_ref):
        try:
            seed = seed_from_reference(local_ref, use_gemini=state.get("text_client") is not None)
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
            "provenance": Provenance(
                style_source="reference",
                reference_ref=local_ref,
                seeds=seed.seeds,
            ),
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
    from .intake import _goal_text
    from .product import ProductGroundingError
    from .product_source import collect_materials, extract_product

    with state["tracer"].node("product"):
        # 목적 텍스트에서 URL/라벨을 걷어낸다. 판매 URL의 도메인(예: oliveyoung.co.kr)이 제품
        # LLM 컨텍스트로 새면 소매점명을 브랜드로 오인해 엉뚱한 제품('올리브영 토너패드')을 지어낸다.
        goal = _goal_text(state["objective"].goal)
        plan_dir = _plan_asset_dir(state)
        url = (state.get("product_url") or "").strip()
        local_img = state.get("product_image")
        # 제품 이름이 실제로 주어졌는지(사용자 서술). "product"는 URL/이미지만 있고 이름은 없을 때
        # intake가 넣는 자리표시자라 '이름 없음'으로 본다.
        raw_name = (state["product"].name or "").strip()
        has_name = bool(raw_name) and raw_name.lower() != "product"

        product = None
        refs: list[str] = []  # 스크래핑한 실제 제품 사진(상위 2장) + 사용자가 준 로컬 제품 이미지
        materials = None
        if url:
            # 제품 URL이 주어졌으면 그 실제 판매 페이지에서 제품을 뽑는 게 최우선이다. 순간적
            # 실패에도 브리프로 '가짜 제품'을 지어내면 안 된다. 다만 GenerationInput처럼 사용자가
            # 제품명/설명을 구조화해서 함께 준 경우는 그 명시 설명을 근거로 계속 진행할 수 있다.
            for _ in range(2):
                materials = collect_materials(url, plan_dir)
                if materials is not None:
                    break
            if materials is None:
                if not local_img and not has_name:
                    raise ProductGroundingError(
                        f"제품 URL을 읽지 못했습니다: {url}\n실제 제품 페이지를 스크래핑하지 못해 "
                        "제품을 임의로 추정하지 않고 중단합니다. 잠시 후 다시 시도하거나 "
                        "다른 제품 URL/이미지를 주세요."
                    )
            else:
                refs = list(materials.image_paths[:2])
                product = extract_product(materials, fallback_name=raw_name)

        if local_img:
            refs.append(local_img)

        if product is None:
            # 여기까지 왔는데 실제 소스가 없으면(제품 URL·이미지·사용자 이름 모두 없음) 제품을
            # 지어내지 않고 실패시킨다(사용자 지시: 제품은 추정 폴백 금지). 소스가 있으면 명시된
            # 것만 추출한다: materials가 있으면 실제 페이지 본문(web_context)이 권위 근거이고,
            # 없으면 사용자가 준 제품 이름/서술만 쓴다. goal은 도메인 누출 방지용 정제본.
            if not materials and not local_img and not has_name:
                raise ProductGroundingError(
                    "홍보할 제품을 확보하지 못했습니다. 제품 판매 URL(권장)이나 제품 이미지, "
                    "또는 구체적인 제품 설명을 주세요. 제품은 임의로 추정하지 않습니다."
                )
            product = derive_product(
                raw_name, goal, state.get("ref_product"),
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
        # 사용자가 준 캐릭터 참조 이미지가 있으면 먼저 그 인물 정체성을 VLM으로 읽어 넘긴다.
        # 이 명시적 캐릭터 의도는 레퍼런스 영상의 부수 인물(ref_subject)보다 우선한다. 안 그러면
        # 성별·나이·인종이 default로 흘러 참조와 다른 사람(예: 남성 참조인데 여성)이 생성된다.
        ref_subject = state.get("ref_subject")
        char_img = state.get("character_image")
        if char_img:
            described = describe_character_image(char_img)
            if described is not None:
                ref_subject = described
        character = derive_character(
            state["objective"].goal, state["product"], ref_subject,
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
    """훅이 스토리에 안 맞고 재시도 여유가 있으면 hook으로 되돌아가 핑퐁한다.

    핑퐁이 끝나면 "forward"를 돌려준다. 이 신호를 어느 노드로 보낼지는 그래프마다 다르게
    매핑한다(plan은 style 보정으로, replan은 narration으로). _route_after_storyboard를 plan과
    replan이 공유하므로, 반환값을 특정 노드명으로 박지 않고 중립 신호로 둔다.
    """
    if state.get("text_client") is None:
        return "forward"
    if state.get("hook_feedback") and state.get("hook_attempts", 0) < MAX_HOOK_ATTEMPTS:
        return "hook"
    return "forward"


def _style_node(state: PlanState) -> dict:
    """style 초안(핵심 노드). hook·story 앞에서 style이 반드시 채워지게 한다.

    레퍼런스가 있으면 분석 seed의 측정 style이 정본이므로 그대로 둔다(측정값을 덮지 않는다).
    없으면 LLM이 목적·제품·캐릭터로 예비 style을 저술해 hook/story가 방향을 갖게 한다. LLM이
    없으면 결정론 기본값으로 채운다. style은 이 시스템의 핵심 축이라 절대 비워 두지 않는다.
    """
    from .style import author_style, ensure_style_defaults

    style = state["style"]
    provenance = state.get("provenance")
    src = getattr(provenance, "style_source", "llm") if provenance else "llm"
    if src == "reference" and style.tone:
        return {"style": style}  # 레퍼런스 측정 style은 정본, 덮지 않는다.
    text_client = state.get("text_client")
    if text_client is None:
        return {"style": ensure_style_defaults(style, state.get("storyboard"), state["meta"])}
    with state["tracer"].node("style"):
        try:
            authored = author_style(
                text_client, objective=state["objective"], product=state["product"],
                character=state["character"], meta=state["meta"], base=style,
            )
        except Exception:
            return {"style": ensure_style_defaults(style, state.get("storyboard"), state["meta"])}
        return {"style": authored}


def _style_refine_node(state: PlanState) -> dict:
    """style 보정. 확정된 hook·story를 극대화하도록 style을 다듬는다(레퍼런스 없을 때만).

    레퍼런스가 있으면 측정 style이 정본이라 손대지 않는다. LLM이 없으면 초안 style을 유지한다.
    replan에서도 같은 보정이 필요하나, replan 그래프는 별도로 이 노드를 배선한다.
    """
    from .style import author_style

    style = state["style"]
    provenance = state.get("provenance")
    src = getattr(provenance, "style_source", "llm") if provenance else "llm"
    text_client = state.get("text_client")
    if src == "reference" or text_client is None:
        return {}  # 변경 없음(레퍼런스 정본 유지 / LLM 부재)
    with state["tracer"].node("style_refine"):
        try:
            refined = author_style(
                text_client, objective=state["objective"], product=state["product"],
                character=state["character"], meta=state["meta"], base=style,
                storyboard=state.get("storyboard"), hook=style.hook,
            )
        except Exception:
            return {}
        return {"style": refined}


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
                brief=state["objective"].goal,
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
        ("style", _style_node), ("style_refine", _style_refine_node),
        ("music", _music_node), ("hook", _hook_node), ("storyboard", _storyboard_node),
        ("narration", _narration_node), ("write_profile", _write_node),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_edge("intake", "reference_seed")
    g.add_edge("reference_seed", "product")
    g.add_edge("product", "character")
    g.add_edge("character", "environment")
    # style 초안은 hook·story 앞에 둔다(style이 방향을 먼저 잡는다). 핑퐁이 끝나면 style_refine
    # 이 확정된 hook·story에 맞춰 style을 보정한 뒤 narration으로 넘어간다.
    g.add_edge("environment", "style")
    g.add_edge("style", "hook")
    g.add_edge("hook", "storyboard")
    g.add_conditional_edges(
        "storyboard", _route_after_storyboard, {"hook": "hook", "forward": "style_refine"}
    )
    g.add_edge("style_refine", "narration")
    # music은 plan의 마지막 노드다: 확정 훅·스토리·나레이션을 보고 음악을 정한 뒤 write로.
    g.add_edge("narration", "music")
    g.add_edge("music", "write_profile")
    g.add_edge("write_profile", END)
    return g.compile()
