"""plan 오케스트레이터(워킹 스켈레톤). 그래프 위상은 정적, 게이트는 일반화.

흐름: intake -> (concept/hook/assets/env/storyboard/scripting) -> profile_assembly -> write.
지금은 순차 함수 + 스텁 모델이다. LangGraph 노드/인터럽트와 실제 LLM·이미지 호출은
Milestone 2에서 같은 인터페이스 뒤에 붙인다.
"""

from __future__ import annotations

from pathlib import Path

from .gates import GateConfig
from .image_client import ImageClient
from .intake import intake
from .profile_assembly import assemble_profile, write_profile
from .run_paths import create_run_dir, make_run_id
from .schema import (
    EnvironmentSpec,
    HookRequest,
    InputMeta,
    ModelSpec,
    ProductSpec,
    Provenance,
    StyleDimensions,
)
from .storyboard import build_storyboard, generate_panel_images, needs_panel_images
from .text_client import TextClient


def run_planning(
    raw: str,
    outputs_root: str,
    *,
    gate: GateConfig,
    text_client: TextClient | None = None,
    image_client: ImageClient | None = None,
) -> Path:
    result = intake(raw)
    if result.objective is None:
        raise ValueError("objective(영상 목적)는 필수다. 입력이 비었다.")

    product = ProductSpec(name=(result.product.source or "product"))
    # 기본 캐릭터: 자연스러운 내추럴함이 매력인 동안의 20대 초중반 여성(specs/trd.md 기본 포맷).
    character = ModelSpec(
        age="early-to-mid 20s",
        gender="female",
        look="naturally pretty, effortless natural look with minimal makeup, "
        "youthful baby face, warm approachable vibe",
    )
    # 장소 언급이 없으면 기본 환경은 등장인물 본인 방(실내)이다(specs/trd.md 기본 제작 포맷).
    environment = EnvironmentSpec(
        location="the creator's own bedroom, indoor",
        lighting="soft natural indoor light",
    )
    meta = InputMeta()
    style = StyleDimensions()
    provenance = Provenance(
        style_source="reference" if result.reference_ref else "llm",
        reference_ref=result.reference_ref,
    )

    if text_client is not None:
        from .hook import generate_hooks

        hooks = generate_hooks(
            HookRequest(product=product, tone=style.tone, duration_sec=meta.duration_sec, count=2),
            text_client,
        )
        if hooks.candidates:
            style.hook = hooks.candidates[0]

    # 스토리보드/콘티는 항상 채운다(텍스트 패널). 컷별 이미지는 복잡한 멀티컷일 때만.
    storyboard = build_storyboard(
        meta=meta,
        style=style,
        product=product,
        character=character,
        environment=environment,
        category=None,  # 카테고리 추론은 concept 노드(추후)가 채운다
    )
    narrative_arc = [p.beat for p in storyboard.panels if p.beat]

    run_id = make_run_id(result.objective.goal)
    out_dir = create_run_dir(outputs_root, run_id)

    if image_client is not None and needs_panel_images(storyboard):
        generate_panel_images(
            storyboard,
            character_image=None,
            product_image=None,
            image_client=image_client,
            out_dir=str(out_dir),
        )

    profile = assemble_profile(
        {
            "objective": result.objective,
            "product": product,
            "character": character,
            "style": style,
            "narrative_arc": narrative_arc,
            "storyboard": storyboard,
            "provenance": provenance,
        }
    )

    return write_profile(profile, out_dir, run_id)
