"""입력 판별. 텍스트 브리프/단일 에셋/JSON 경로를 Objective+AssetInput으로 푼다.

판별 규칙 정본은 specs/product-design.md. 라벨 우선, 없으면 미디어 종류로 추정.
기본 로케일은 영어·미국.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schema import AssetInput, Objective

_URL = re.compile(r"https?://\S+")
_PATH = re.compile(r"\.?/?\S+\.(?:mp4|mov|jpg|jpeg|png|webp)", re.IGNORECASE)
_VIDEO_EXT = (".mp4", ".mov")


@dataclass
class IntakeResult:
    objective: Objective | None
    character: AssetInput
    product: AssetInput
    reference_ref: str | None
    raw_brief: str | None


def _labeled(raw: str, labels: list[str]) -> str | None:
    for label in labels:
        m = re.search(rf"{label}\s*[:：]\s*(\S+)", raw)
        if m:
            return m.group(1)
    return None


def intake(raw: str) -> IntakeResult:
    product_src = _labeled(raw, ["제품", "product"])
    character_src = _labeled(raw, ["캐릭터", "character", "모델"])
    ref_src = _labeled(raw, ["레퍼런스 영상", "레퍼런스", "reference"])
    if ref_src is None:
        for tok in _URL.findall(raw) + _PATH.findall(raw):
            if tok.lower().endswith(_VIDEO_EXT):
                ref_src = tok
                break
    product = AssetInput(
        kind="product", source=product_src, present=product_src is not None
    )
    character = AssetInput(
        kind="character", source=character_src, present=character_src is not None
    )
    objective = Objective(goal=raw.strip()) if raw.strip() else None
    return IntakeResult(
        objective=objective,
        character=character,
        product=product,
        reference_ref=ref_src,
        raw_brief=raw.strip() or None,
    )
