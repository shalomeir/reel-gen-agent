"""plan 오케스트레이터(워킹 스켈레톤). 그래프 위상은 정적, 게이트는 일반화.

흐름: intake -> (concept/hook/assets/env/storyboard/scripting) -> profile_assembly -> write.
지금은 순차 함수 + 스텁 모델이다. LangGraph 노드/인터럽트와 실제 LLM·이미지 호출은
Milestone 2에서 같은 인터페이스 뒤에 붙인다.
"""

from __future__ import annotations

from pathlib import Path

from .gates import GateConfig
from .intake import intake
from .profile_assembly import assemble_profile, write_profile
from .run_paths import create_run_dir, make_run_id
from .schema import HookRequest, ProductSpec, Provenance, StyleDimensions
from .text_client import TextClient


def run_planning(
    raw: str,
    outputs_root: str,
    *,
    gate: GateConfig,
    text_client: TextClient | None = None,
) -> Path:
    result = intake(raw)
    if result.objective is None:
        raise ValueError("objective(영상 목적)는 필수다. 입력이 비었다.")

    product = ProductSpec(name=(result.product.source or "product"))
    style = StyleDimensions()
    provenance = Provenance(
        style_source="reference" if result.reference_ref else "llm",
        reference_ref=result.reference_ref,
    )

    if text_client is not None:
        from .hook import generate_hooks

        hooks = generate_hooks(
            HookRequest(product=product, tone=style.tone, duration_sec=18.0, count=2),
            text_client,
        )
        if hooks.candidates:
            style.hook = hooks.candidates[0]

    profile = assemble_profile(
        {
            "objective": result.objective,
            "product": product,
            "style": style,
            "provenance": provenance,
        }
    )

    run_id = make_run_id(result.objective.goal)
    out_dir = create_run_dir(outputs_root, run_id)
    return write_profile(profile, out_dir, run_id)
