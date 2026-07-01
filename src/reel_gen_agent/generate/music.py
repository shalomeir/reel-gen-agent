"""음악(BGM) 정의 노드: 영상 목적·톤·제품·레퍼런스로 MusicSpec을 LLM이 정한다.

원칙(사용자 지시): "팝으로", "밝게" 같은 스타일 선택을 코드나 프롬프트에 하드코딩하지
않는다. 노드마다 LLM(Gemini/Claude)이 문맥에 맞는 음악(장르·무드·다이내믹)을 고른다.
레퍼런스가 있으면 그 음악 무드를 힌트로 반영한다. LLM이 없을 때만 최소한의 중립값을 쓴다.
"""

from __future__ import annotations

import json

from .schema import ModelSpec, MusicSpec, ProductSpec
from .text_client import TextClient

_PROMPT = (
    "Choose background music (an instrumental bed under a voiceover) for a vertical short-form "
    "beauty ad. Decide the genre/style, mood, and dynamics that best fit this specific video and "
    "its on-camera creator; do not default to any fixed genre.\n"
    "Brief: {brief}\nProduct: {product}\nTone: {tone}\nCreator: {character}\n{ref}\n"
    'Output raw JSON only (no markdown, no prose): '
    '{{"style": str, "mood": str, "type": str, "dynamics": "flat"|"build"}}. '
    "style is the genre/production style; type is a short descriptor; dynamics is whether energy "
    "rises to a payoff (build) or stays even (flat)."
)


def _extract_json(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


def derive_music(
    brief: str,
    product: ProductSpec,
    tone: list[str],
    reference_music: MusicSpec | None,
    text_client: TextClient | None,
    character: ModelSpec | None = None,
) -> MusicSpec:
    """브리프·톤·레퍼런스로 MusicSpec을 도출한다. LLM 우선, 실패/부재 시 레퍼런스/중립 폴백.

    tempo(bpm)는 컷 리듬과 맞춰야 하므로 여기서 정하지 않는다(execute가 컷 주기로 산정하거나
    레퍼런스 bpm을 쓴다). 레퍼런스 tempo가 있으면 보존한다.
    """
    ref = reference_music or MusicSpec()
    ref_hint = ""
    if ref.mood or ref.style or ref.dynamics:
        ref_hint = (
            f"Reference music (a hint, adapt to this brief): mood={ref.mood or 'unknown'}, "
            f"style={ref.style or 'unknown'}, dynamics={ref.dynamics or 'unknown'}."
        )

    if text_client is not None:
        try:
            from .character import character_brief

            raw = text_client.complete(
                _PROMPT.format(
                    brief=brief, product=product.name, tone=", ".join(tone) or "unspecified",
                    character=(character_brief(character) if character else "unspecified"),
                    ref=ref_hint,
                ),
                temperature=0.7,
            )
            data = json.loads(_extract_json(raw))
            style = str(data.get("style") or "").strip() or ref.style
            mood = str(data.get("mood") or "").strip() or ref.mood
            type_ = str(data.get("type") or "").strip() or ref.type
            dynamics = str(data.get("dynamics") or "").strip() or ref.dynamics
            if style or mood or type_:
                return MusicSpec(
                    mood=mood, style=style, type=type_, dynamics=dynamics, tempo=ref.tempo
                )
        except Exception:
            pass

    # LLM이 없거나 실패: 레퍼런스 음악을 그대로 쓰고, 그것도 없으면 톤 첫 단어를 무드로만 둔다.
    if ref.mood or ref.style or ref.dynamics or ref.tempo:
        return ref
    return MusicSpec(mood=(tone[0] if tone else None), tempo=ref.tempo)
