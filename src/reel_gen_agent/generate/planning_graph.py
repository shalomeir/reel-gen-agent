"""plan 오케스트레이터(워킹 스켈레톤). 그래프 위상은 정적, 게이트는 일반화.

흐름: intake -> (concept/hook/assets/env/storyboard/scripting) -> profile_assembly -> write.
지금은 순차 함수 + 스텁 모델이다. LangGraph 노드/인터럽트와 실제 LLM·이미지 호출은
Milestone 2에서 같은 인터페이스 뒤에 붙인다.
"""

from __future__ import annotations

from pathlib import Path

from ..analysis.profile import Subject
from .asset_bible import build_asset_bible
from .character import character_brief, derive_character, voice_persona
from .gates import GateConfig
from .image_client import ImageClient
from .intake import intake
from .music import derive_music
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
    # 장소 언급이 없으면 기본 환경은 등장인물 본인 방(실내)이다(specs/trd.md 기본 제작 포맷).
    environment = EnvironmentSpec(
        location="the creator's own bedroom, indoor",
        lighting="soft natural indoor light",
    )
    meta = InputMeta()
    style = StyleDimensions()
    music = MusicSpec()
    cut_count: int | None = None
    delivery = "voiceover"  # 기본은 나레이션. 레퍼런스가 온카메라 발화면 시딩이 바꾼다.
    ref_subject: Subject | None = None  # 레퍼런스 등장 인물(캐릭터 노드 입력)
    provenance = Provenance(
        style_source="reference" if result.reference_ref else "llm",
        reference_ref=result.reference_ref,
    )

    # 레퍼런스가 있으면 최대한 레퍼런스에서 베이스라인을 시딩한다(스타일/메타/음악/컷수/후크/인물).
    ref = result.reference_ref
    if ref and Path(ref).exists():
        try:
            seed = seed_from_reference(ref, use_gemini=text_client is not None)
            meta, style, music = seed.meta, seed.style, seed.music
            cut_count = seed.cut_count or None
            delivery = seed.delivery  # 레퍼런스 발화 방식(온카메라/나레이션/무음)을 따른다
            ref_subject = seed.subject  # 레퍼런스 인물 -> 캐릭터 노드가 최대한 반영
            provenance.seeds = seed.seeds
        except Exception:
            pass  # 시딩 실패 시 기본값으로 진행(파이프라인은 끝까지 돈다).

    # 캐릭터 노드: 레퍼런스 인물이 있으면 최대한 반영하고, 없으면 LLM이 브리프에서 도출한다.
    # 아무 단서 없으면 기본값(매력적인 20대 초반 미국 여성). 하드코딩하지 않는다(사용자 지시).
    character = derive_character(result.objective.goal, product, ref_subject, text_client)

    # 음악 노드: 장르·무드·다이내믹을 LLM이 문맥(브리프·톤·주인공 캐릭터)으로 정한다(스타일
    # 하드코딩 금지). 레퍼런스 음악은 힌트로만. bpm은 execute가 컷 리듬으로 맞춘다.
    music = derive_music(
        result.objective.goal, product, style.tone, music, text_client, character=character
    )

    # 후크: 유형·문구는 LLM이 제품·목적·톤에 맞춰 유연하게 고른다(하드코딩 X, temperature로
    # 다양성). 레퍼런스가 있으면 그 첫 3초 시각 컨셉(visual_direction)·문구·윈도를 LLM이 고른
    # 후크에 얹어, "유형은 LLM 선택 + 비주얼은 레퍼런스"로 합친다. LLM이 없으면 레퍼런스 후크를
    # 그대로 쓰고, 둘 다 없으면 후크 없이 둔다(하드코딩 유형 강제 안 함).
    ref_hook = style.hook  # 레퍼런스 시딩 후크(있으면). 유형은 아래서 LLM이 다시 고른다.
    if text_client is not None:
        from .hook import generate_hooks

        try:
            hooks = generate_hooks(
                HookRequest(
                    product=product,
                    tone=style.tone,
                    character=character_brief(character),  # 주인공 문맥 공유
                    language=meta.language,  # 기본 영어(en). 명시 요청 시만 다른 언어.
                    duration_sec=meta.duration_sec,
                    count=2,
                ),
                text_client,
            )
        except Exception:
            hooks = None  # LLM 후크 실패 -> 레퍼런스 후크(또는 None) 유지
        if hooks and hooks.candidates:
            chosen = hooks.candidates[0]
            if ref_hook is not None:
                # 레퍼런스의 첫 3초 비주얼·문구·윈도를 얹는다(유형은 LLM이 고른 것을 유지).
                if ref_hook.visual_direction:
                    chosen.visual_direction = ref_hook.visual_direction
                if ref_hook.headline:
                    chosen.headline = ref_hook.headline
                if ref_hook.bottom_caption:
                    chosen.bottom_caption = ref_hook.bottom_caption
                chosen.window_sec = ref_hook.window_sec
            style.hook = chosen

    narration = NarrationSpec(
        delivery=delivery,
        # voice 성향을 캐릭터에서 유도한다(성별·나이·분위기). TTS가 이 페르소나로 보이스를 고른다.
        voice=VoiceSpec(from_character=True, type=voice_persona(character)),
    )

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

    # 나레이션: 스토리보드 비트에 맞춰 패널별 짧은 대사를 생성한다(비트별 정렬 배치의 근거).
    # LLM이 패널 수만큼 짧은 라인(비주얼-only 비트는 빈 문자열)을 내고, 각 라인을 그 패널에
    # 매핑한다. execute가 각 라인을 TTS해 패널 t_start에 깔아 콘티에 맞물리게 한다.
    if text_client is not None:
        narration.lines = _narration_lines(
            text_client, product, style, meta, [p.beat or "" for p in storyboard.panels],
            character=character,
        )

    run_id = make_run_id(result.objective.goal)
    out_dir = create_run_dir(outputs_root, run_id)
    # plan 산출물은 run 루트의 plan/ 하위에 모은다(ReelProfile + 캐릭터·제품·환경·스틸 콘티).
    # 결과물 3종(final/report/upload)은 execute가 run 루트에 떨어뜨려, 무엇이 plan이고 무엇이
    # 결과물인지 한눈에 보이게 한다([output 폴더 구조] 사용자 지시).
    plan_dir = out_dir / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)

    # asset_bible: 캐릭터 정면샷 + 제품 이미지를 생성한다(image_client 있을 때). 이 에셋이
    # execute의 컷별 스틸 생성에서 reference·폴백으로 쓰인다. 없으면 빈 에셋으로 둔다.
    asset_bible = build_asset_bible(
        character, product, environment, image_client, str(plan_dir), palette=style.palette
    )

    profile = assemble_profile(
        {
            "objective": result.objective,
            "product": product,
            "meta": meta,  # 스토리보드가 쓴 meta를 그대로 실어 길이 정렬을 보장한다
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

    return write_profile(profile, plan_dir, run_id)


def _narration_lines(
    text_client: TextClient,
    product: ProductSpec,
    style: StyleDimensions,
    meta: InputMeta,
    beats: list[str],
    character: ModelSpec | None = None,
) -> list[NarrationLine]:
    """패널 비트에 맞춘 짧은 나레이션 라인을 생성한다(비주얼-only 비트는 제외).

    주인공 캐릭터(성향)를 문맥으로 넣어 "이 캐릭터라면 이렇게 말한다" 톤의 대사를 만든다.
    LLM이 beats와 같은 길이의 JSON 배열(각 원소는 짧은 대사 또는 "")을 내면, 비어 있지 않은
    라인만 그 패널 인덱스에 매핑한다. 실패하면 빈 목록(voice 없이 진행).
    """
    import json

    from .character import character_brief
    from .hook import _extract_json

    tone_hint = ", ".join(style.tone) if style.tone else "natural, authentic"
    persona = character_brief(character) if character else "an attractive early-20s US creator"
    prompt = (
        f"You are {persona}, speaking a first-person voiceover for a {meta.duration_sec:.0f}-second "
        f"vertical beauty short about {product.name}. Speak in that persona's voice.\n"
        f"Tone: {tone_hint}, natural UGC. Language: {meta.language} (default US English).\n"
        f"The video has {len(beats)} cuts with these beats in order: {beats}.\n"
        "Write ONE short spoken line (3-8 words) per cut that matches that beat, or an empty "
        "string for purely visual cuts with no voice. The lines should flow as one natural "
        "narration across the video (hook first, call-to-action last).\n"
        f'Return raw JSON only: {{"lines": ["...", "", "..."]}} with exactly {len(beats)} items.'
    )
    try:
        raw = text_client.complete(prompt, temperature=0.7)
        data = json.loads(_extract_json(raw))
        arr = data.get("lines", []) if isinstance(data, dict) else []
    except Exception:
        return []
    lines: list[NarrationLine] = []
    for i, text in enumerate(arr[: len(beats)]):
        if isinstance(text, str) and text.strip():
            lines.append(NarrationLine(panel_index=i, text=text.strip()))
    return lines
