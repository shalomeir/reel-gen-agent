"""plan 노드들이 공유하는 순수 함수. 그래프(plan_graph)와 레거시 오케스트레이터가 함께 쓴다."""

from __future__ import annotations

import json

from .character import character_brief
from .hook import _extract_json
from .schema import InputMeta, ModelSpec, NarrationLine, ProductSpec, StyleDimensions
from .text_client import TextClient


def narration_lines(
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
