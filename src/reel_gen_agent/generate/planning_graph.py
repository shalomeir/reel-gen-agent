"""plan 오케스트레이터(워킹 스켈레톤). 그래프 위상은 정적, 게이트는 일반화.

흐름: intake -> (concept/hook/assets/env/storyboard/scripting) -> profile_assembly -> write.
지금은 순차 함수 + 스텁 모델이다. LangGraph 노드/인터럽트와 실제 LLM·이미지 호출은
Milestone 2에서 같은 인터페이스 뒤에 붙인다.
"""

from __future__ import annotations

from pathlib import Path

from .asset_bible import build_asset_bible
from .gates import GateConfig
from .image_client import ImageClient
from .intake import intake
from .profile_assembly import assemble_profile, write_profile
from .reference_seed import seed_from_reference
from .run_paths import create_run_dir, make_run_id
from .schema import (
    EnvironmentSpec,
    HookRequest,
    InputMeta,
    ModelSpec,
    MusicSpec,
    NarrationLine,
    NarrationSpec,
    ProductSpec,
    Provenance,
    StyleDimensions,
    VoiceSpec,
)
from .storyboard import build_storyboard
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
    music = MusicSpec()
    cut_count: int | None = None
    provenance = Provenance(
        style_source="reference" if result.reference_ref else "llm",
        reference_ref=result.reference_ref,
    )

    # 레퍼런스가 있으면 최대한 레퍼런스에서 베이스라인을 시딩한다(스타일/메타/음악/컷수/후크).
    ref = result.reference_ref
    if ref and Path(ref).exists():
        try:
            seed = seed_from_reference(ref, use_gemini=text_client is not None)
            meta, style, music = seed.meta, seed.style, seed.music
            cut_count = seed.cut_count or None
            provenance.seeds = seed.seeds
        except Exception:
            pass  # 시딩 실패 시 기본값으로 진행(파이프라인은 끝까지 돈다).

    # 후크: 레퍼런스 후크가 없고 LLM이 있으면 생성한다(레퍼런스 후크는 시딩에서 이미 채워짐).
    if style.hook is None and text_client is not None:
        from .hook import generate_hooks

        hooks = generate_hooks(
            HookRequest(product=product, tone=style.tone, duration_sec=meta.duration_sec, count=2),
            text_client,
        )
        if hooks.candidates:
            style.hook = hooks.candidates[0]

    # 나레이션 스크립트: 기본 전달은 voiceover. LLM이 있으면 짧은 대사 스크립트를 생성한다.
    narration = NarrationSpec(
        delivery="voiceover",
        voice=VoiceSpec(from_character=True, type=(character.look or None)),
    )
    if text_client is not None:
        try:
            script = text_client.complete(
                f"Write a short, upbeat first-person narration voiceover script in English "
                f"for a {meta.duration_sec:.0f}-second vertical beauty short about "
                f"{product.name}. 2-3 short punchy sentences, natural UGC tone, no emojis, "
                f"no stage directions. Return only the narration text.",
                temperature=0.8,
            )
            if script.strip():
                narration.lines = [NarrationLine(panel_index=0, text=script.strip())]
        except Exception:
            pass

    # 스토리보드/콘티는 항상 채운다(텍스트 패널). 레퍼런스 컷 수가 있으면 그 수에 맞춘다.
    storyboard = build_storyboard(
        meta=meta,
        style=style,
        product=product,
        character=character,
        environment=environment,
        category=None,  # 카테고리 추론은 concept 노드(추후)가 채운다
        cut_count=cut_count,
    )
    narrative_arc = [p.beat for p in storyboard.panels if p.beat]

    run_id = make_run_id(result.objective.goal)
    out_dir = create_run_dir(outputs_root, run_id)

    # asset_bible: 캐릭터 정면샷 + 제품 이미지를 생성한다(image_client 있을 때). 이 에셋이
    # execute의 컷별 스틸 생성에서 reference·폴백으로 쓰인다. 없으면 빈 에셋으로 둔다.
    asset_bible = build_asset_bible(
        character, product, environment, image_client, str(out_dir), palette=style.palette
    )

    profile = assemble_profile(
        {
            "objective": result.objective,
            "product": product,
            "character": character,
            "style": style,
            "narrative_arc": narrative_arc,
            "asset_bible": asset_bible,
            "storyboard": storyboard,
            "narration": narration,
            "music": music,
            "provenance": provenance,
        }
    )

    return write_profile(profile, out_dir, run_id)
