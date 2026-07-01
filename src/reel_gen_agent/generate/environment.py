"""환경(배경) 노드: 촬영 장소·조명·무드를 브리프·제품·캐릭터로 LLM이 정한다.

원칙(사용자 지시): 장소를 코드에 하드코딩("항상 침실")하지 않는다. 브리프가 장소를 말하면
그걸 따르고, 아니면 제품·캐릭터에 어울리는 장소를 LLM이 고른다. 단서가 전혀 없을 때만
기본값(크리에이터 본인 방, 실내)을 쓴다. 실외/스튜디오/욕실 등 input에 따라 유연하게 바뀐다.
"""

from __future__ import annotations

import json

from .schema import EnvironmentSpec, ModelSpec, ProductSpec
from .text_client import TextClient

# 단서가 전혀 없을 때만 쓰는 기본 환경(specs/trd.md 기본 제작 포맷).
DEFAULT_ENVIRONMENT = EnvironmentSpec(
    location="the creator's own bedroom, indoor",
    lighting="soft natural indoor light",
)

_PROMPT = (
    "Choose the filming environment for a vertical short-form beauty ad. Decide the location,"
    " lighting, and mood that fit this brief, product, and creator. If the brief names a place,"
    " use it. Do not default to a fixed place.\n"
    "Brief: {brief}\nProduct: {product}\nCreator: {character}\n"
    'Output raw JSON only (no markdown, no prose): '
    '{{"location": str, "lighting": str, "mood": str}}.'
)


def _extract_json(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


def derive_environment(
    brief: str,
    product: ProductSpec,
    character: ModelSpec | None,
    text_client: TextClient | None,
) -> EnvironmentSpec:
    """브리프·제품·캐릭터로 환경을 도출한다. LLM 우선, 실패/부재 시 기본값."""
    if text_client is None:
        return DEFAULT_ENVIRONMENT.model_copy()
    try:
        from .character import character_brief

        raw = text_client.complete(
            _PROMPT.format(
                brief=brief,
                product=product.name,
                character=(character_brief(character) if character else "unspecified"),
            ),
            temperature=0.7,
        )
        data = json.loads(_extract_json(raw))
        location = str(data.get("location") or "").strip()
        if not location:
            raise ValueError("empty location")
        return EnvironmentSpec(
            location=location,
            lighting=str(data.get("lighting") or DEFAULT_ENVIRONMENT.lighting),
            mood=str(data.get("mood") or "") or None,
        )
    except Exception:
        return DEFAULT_ENVIRONMENT.model_copy()
