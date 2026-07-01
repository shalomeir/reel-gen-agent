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
    delivery_tone: str | None = None,
    delivery_pace: str | None = None,
) -> list[NarrationLine]:
    """패널 비트에 맞춘 짧은 나레이션 라인을 생성한다(비주얼-only 비트는 제외).

    주인공 캐릭터(성향)를 문맥으로 넣어 "이 캐릭터라면 이렇게 말한다" 톤의 대사를 만든다.
    레퍼런스 발화의 결(delivery_tone/pace)이 있으면 그 결에 맞는 어휘·호흡으로 쓰게 한다
    (예: whispered soft -> 짧고 나직한 문장). LLM이 beats와 같은 길이의 JSON 배열을 내면,
    비어 있지 않은 라인만 그 패널 인덱스에 매핑한다. 실패하면 빈 목록(voice 없이 진행).
    """
    tone_hint = ", ".join(style.tone) if style.tone else "natural, authentic"
    persona = character_brief(character) if character else "an attractive early-20s US creator"
    # 레퍼런스 발화의 결을 대사 어휘·호흡에 반영한다(코드가 스타일을 박지 않고 관측을 흘린다).
    delivery_bits = ", ".join(b for b in (delivery_tone, delivery_pace) if b)
    delivery_hint = (
        f"Delivery to write for: {delivery_bits}. Match this delivery in word choice and rhythm "
        "(e.g. a whispered/soft/slow delivery uses fewer, quieter, unhurried words; an energetic "
        "delivery uses punchier lines).\n"
        if delivery_bits
        else ""
    )
    prompt = (
        f"You are {persona}, a real short-form creator (influencer / YouTuber / TikToker) speaking a "
        f"first-person voiceover for a {meta.duration_sec:.0f}-second vertical beauty short that "
        f"involves {product.name}. You are casually telling your followers what YOU genuinely felt "
        "and noticed using it — like talking to a friend, sharing a real experience.\n"
        f"Tone: {tone_hint}, authentic UGC, conversational.\n"
        f"{delivery_hint}"
        "Write like a REAL creator sharing an honest reaction, NOT a TV ad or a product brochure. "
        "First person ('I', 'my'), genuine feelings and specific sensory impressions, understated and "
        "real. Do NOT explain/pitch the product like an advertiser. Avoid ad copy and marketing "
        "cliches (no 'revolutionary', 'must-have', 'game-changer', 'transform your life', "
        "'say goodbye to'), and no hard sell or imperative CTA ('buy now', 'get yours', 'link in "
        "bio' as a command). If anything, end on a low-key personal note ('honestly obsessed', "
        "'kind of a staple for me now') — only if it feels natural, not a sales close.\n"
        f"Language: {meta.language} (default US English). The video has {len(beats)} cuts with these "
        f"beats in order: {beats}.\n"
        "Write ONE short spoken line (3-8 words) per cut, the way this creator would actually say it, "
        "or an empty string for purely visual cuts with no voice. Lines flow as one natural, honest "
        "narration.\n"
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
