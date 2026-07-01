"""plan 노드들이 공유하는 순수 함수. 그래프(plan_graph)와 레거시 오케스트레이터가 함께 쓴다."""

from __future__ import annotations

import json

from .character import character_brief
from .hook import _extract_json
from .schema import InputMeta, ModelSpec, NarrationLine, ProductSpec, StyleDimensions
from .text_client import TextClient

# 나레이션 발화 속도(단어/초). 자연스러운 UGC 발화에 대사 사이 쉼까지 포함한 보수적 값이다.
# 컷마다 한 줄씩 쓰면(빠른 몽타주는 컷이 많다) 말하는 시간이 영상을 훌쩍 넘어 끝에서 영상이
# 얼어붙는다. 이 속도로 영상 길이 안에 다 들어갈 단어 수만 쓰게 예산을 잡는다.
_NARRATION_WORDS_PER_SEC = 2.0


def _narration_word_budget(duration_sec: float) -> int:
    """영상 길이에 맞춘 전체 나레이션 단어 예산. 이 안에서만 대사를 쓴다(과다 대사 방지)."""
    return max(6, int(round(duration_sec * _NARRATION_WORDS_PER_SEC)))


# 명시적으로 '직접 광고 톤'을 원한다는 브리프 신호. 기본 나레이션은 광고 아닌 자연스러운 UGC
# 톤이고, 이런 신호가 있을 때만 광고 문구 억제를 해제한다(사용자 지시). 이 프로덕트 자체가 광고
# 생성기라 광범위한 "광고"가 아니라 '광고처럼/하드셀/홍보 문구' 같은 명시 신호만 잡는다.
_EXPLICIT_AD_HINTS = (
    "광고 톤", "광고처럼", "광고 문구", "광고스럽", "직접 광고", "하드셀", "홍보 문구", "홍보성",
    "세일즈", "판매 문구", "ad copy", "ad-style", "hard sell", "hard-sell", "salesy",
    "commercial tone", "promotional copy",
)


def _is_explicit_ad(brief: str) -> bool:
    """브리프가 명시적으로 광고 톤을 원하는지 판단한다(기본은 False = 자연스러운 UGC 톤)."""
    b = (brief or "").lower()
    return any(h.lower() in b for h in _EXPLICIT_AD_HINTS)


def narration_lines(
    text_client: TextClient,
    product: ProductSpec,
    style: StyleDimensions,
    meta: InputMeta,
    beats: list[str],
    character: ModelSpec | None = None,
    delivery_tone: str | None = None,
    delivery_pace: str | None = None,
    brief: str = "",
) -> list[NarrationLine]:
    """패널 비트에 맞춘 짧은 나레이션 라인을 생성한다(비주얼-only 비트는 제외).

    주인공 캐릭터(성향)를 문맥으로 넣어 "이 캐릭터라면 이렇게 말한다" 톤의 대사를 만든다.
    레퍼런스 발화의 결(delivery_tone/pace)이 있으면 그 결에 맞는 어휘·호흡으로 쓰게 한다
    (예: whispered soft -> 짧고 나직한 문장). LLM이 beats와 같은 길이의 JSON 배열을 내면,
    비어 있지 않은 라인만 그 패널 인덱스에 매핑한다. 실패하면 빈 목록(voice 없이 진행).
    """
    # 대사량을 영상 길이에 맞춰 예산화한다(컷 수가 아니라 발화 시간이 기준). 대략 3초에 한 줄.
    word_budget = _narration_word_budget(meta.duration_sec)
    target_lines = max(2, round(meta.duration_sec / 3.0))
    tone_hint = ", ".join(style.tone) if style.tone else "natural, authentic"
    persona = character_brief(character) if character else "an attractive early-20s US creator"
    # 레퍼런스 발화의 결을 대사 어휘·호흡에 반영한다(코드가 스타일을 박지 않고 관측을 흘린다).
    delivery_bits = ", ".join(b for b in (delivery_tone, delivery_pace) if b)
    delivery_hint = (
        f"REFERENCE delivery (TOP PRIORITY — this is observed from the reference video, follow it "
        f"above the default register): {delivery_bits}. Match this delivery in word choice and "
        "rhythm (e.g. a whispered/soft/slow delivery uses fewer, quieter, unhurried words; an "
        "energetic delivery uses punchier lines).\n"
        if delivery_bits
        else ""
    )
    # 기본은 광고 아닌 자연스러운 크리에이터 톤. 브리프가 명시적으로 광고를 원하면 이 억제를 뺀다.
    if _is_explicit_ad(brief):
        tone_directive = (
            "This is an ad, so promotional copy is fine: you may pitch the product and use a call to "
            "action if it fits, while still sounding like this specific creator (first person, "
            "concrete and specific, not robotic).\n"
        )
    else:
        # 기본(폴백) 레지스터일 뿐이다. 위 Tone(스타일/레퍼런스/입력에서 온 값)을 먼저 따르고,
        # 그게 다른 결을 원하면 그걸 우선한다. 특정 상투구('honestly obsessed', 'I finally found'
        # 류)를 예시로 박지 않는다 — 그런 예시가 매번 같은 문장으로 수렴시키기 때문이다.
        tone_directive = (
            "Follow the Tone above first. If the Tone does not dictate otherwise, write in first "
            "person as this specific creator, concrete and specific, not robotic ad copy. Avoid "
            "generic marketing cliches ('revolutionary', 'must-have', 'game-changer', 'transform "
            "your life', 'say goodbye to') and hard-sell CTAs ('buy now', 'get yours') unless the "
            "brief calls for them. Do not reuse a fixed opener or catchphrase across videos.\n"
        )
    from .product import product_brief

    prompt = (
        f"You are {persona}, a real short-form creator (influencer / YouTuber / TikToker) speaking a "
        f"first-person voiceover for a {meta.duration_sec:.0f}-second vertical short-form video "
        f"about {product.name}. You are casually telling your followers what YOU genuinely felt "
        "and noticed using it — like talking to a friend, sharing a real experience.\n"
        # 제품 알맹이(효능·성분·사용법)를 실어 구체적이고 사실적인 언급이 나오게 한다(빈약한 대사 방지).
        f"About the product (draw on real, specific details; do not overclaim): {product_brief(product)}\n"
        f"Tone: {tone_hint}, authentic UGC, conversational.\n"
        f"{delivery_hint}"
        f"{tone_directive}"
        f"Language: {meta.language} (default US English). The video has {len(beats)} cuts with these "
        f"beats in order: {beats}.\n"
        f"LENGTH BUDGET (critical): the whole voiceover must be at most {word_budget} words TOTAL "
        f"across all lines, so it can be spoken naturally within {meta.duration_sec:.0f} seconds "
        "without rushing. Do NOT write a line for every cut — that overflows the video and the "
        "picture freezes while the voice keeps talking. Leave MOST cuts as empty strings and write "
        f"only about {target_lines} short spoken lines (3-7 words each) on the most important beats "
        "(e.g. the hook, one key impression, and a low-key closing). The lines you do write should "
        "flow together as one natural, honest narration.\n"
        f'Return raw JSON only: {{"lines": ["...", "", "..."]}} with exactly {len(beats)} items '
        "(empty strings for cuts with no voice)."
    )
    try:
        raw = text_client.complete(prompt, temperature=0.7)
        data = json.loads(_extract_json(raw))
        arr = data.get("lines", []) if isinstance(data, dict) else []
    except Exception:
        return []
    # LLM이 예산을 무시하고 과다 대사를 써도 여기서 예산 초과분을 잘라 영상을 넘지 않게 한다
    # (compose의 트랙 캡과 함께 이중 방어). 스토리보드 순서대로 채우다 예산을 넘으면 멈춘다.
    lines: list[NarrationLine] = []
    used_words = 0
    for i, text in enumerate(arr[: len(beats)]):
        if not (isinstance(text, str) and text.strip()):
            continue
        n_words = len(text.split())
        if lines and used_words + n_words > word_budget:
            break  # 이미 한 줄 이상 확보 + 예산 초과 -> 뒤 대사는 버린다(대사 흐름은 앞쪽 유지)
        used_words += n_words
        lines.append(NarrationLine(panel_index=i, text=text.strip()))
    return lines
