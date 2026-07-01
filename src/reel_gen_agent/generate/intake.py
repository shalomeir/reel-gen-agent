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


def _goal_text(raw: str) -> str:
    """라벨(제품:/reference: 등) 값·URL·파일경로를 걷어낸 '목적' 서술 텍스트만 남긴다."""
    text = _URL.sub(" ", raw)
    text = _PATH.sub(" ", text)
    # "라벨: 값" 형태에서 값만 짧게 붙는 제품/캐릭터/레퍼런스 라벨 토큰을 제거(목적 라벨은 보존).
    for label in ("제품", "product", "캐릭터", "character", "모델", "레퍼런스 영상", "레퍼런스", "reference"):
        text = re.sub(rf"{label}\s*[:：]\s*\S+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_PURPOSE_PROMPT = (
    "You validate input for a short-form video ad generator. Does the input clearly state the "
    "PURPOSE/GOAL of the video to make (what it advertises or is for, e.g. a product and the intent)? "
    "A bare filename/URL or a vague 'make a video' is NOT a clear purpose.\n"
    "Input: {brief}\n"
    'Reply raw JSON only: {{"ok": bool, "reason": str}}. reason: if not ok, one line on what is missing.'
)


def validate_purpose(raw: str, text_client=None) -> tuple[bool, str]:
    """입력에 '영상의 목적'이 제대로 서술됐는지 판정한다. (ok, 사유).

    라벨/URL/경로를 걷어낸 목적 텍스트가 너무 얇으면 즉시 거절. LLM이 있으면 목적 명료성을
    한 번 더 판단하고(부실하면 거절), 없으면 최소 단어수 휴리스틱만 쓴다. ok=True면 그 목적만
    으로 나머지(캐릭터·제품·환경·음악 등)를 추론해 ReelProfile을 만든다.
    """
    goal = _goal_text(raw)
    if len(goal.split()) < 3:
        return False, "영상의 목적(무엇을 위한 어떤 영상인지)이 서술되지 않았습니다. 목적을 적어주세요."
    if text_client is not None:
        try:
            import json as _json

            out = text_client.complete(_PURPOSE_PROMPT.format(brief=raw.strip()), temperature=0.0)
            s = out.strip()
            start, end = s.find("{"), s.rfind("}")
            data = _json.loads(s[start : end + 1]) if start != -1 and end > start else {}
            if not bool(data.get("ok", True)):
                return False, str(data.get("reason") or "영상의 목적이 명확하지 않습니다.")
        except Exception:
            pass  # LLM 판정 실패 -> 휴리스틱 통과로 진행
    return True, ""


def intake(raw: str) -> IntakeResult:
    product_src = _labeled(raw, ["제품", "product"])
    character_src = _labeled(raw, ["캐릭터", "character", "모델"])
    ref_src = _labeled(raw, ["레퍼런스 영상", "레퍼런스", "reference"])
    if ref_src is None:
        for tok in _URL.findall(raw) + _PATH.findall(raw):
            if tok.lower().endswith(_VIDEO_EXT):
                ref_src = tok
                break
    product = AssetInput(kind="product", source=product_src, present=product_src is not None)
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
