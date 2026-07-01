"""캐릭터 노드: 입력·레퍼런스에서 등장 인물(ModelSpec)을 도출한다.

원칙(사용자 지시): 하드코딩하지 않는다. 레퍼런스에 인물이 나오면 그 설정(성별·나이대·인종·
외모)을 최대한 가져오고, 없으면 브리프를 보고 LLM이 적합한 캐릭터를 정한다. 아무 단서가
없을 때의 기본값만 코드가 쥐고 있다: 매력적인 20대 초반 미국(서구) 여성.
"""

from __future__ import annotations

import json

from ..analysis.profile import Subject
from .schema import ModelSpec, ProductSpec
from .text_client import TextClient

# 단서가 전혀 없을 때만 쓰는 기본 캐릭터. 인종/국적을 명시해 이미지 모델이 임의로 동양인 등으로
# 흐르지 않게 한다(사용자 지시: 기본은 20대 초반 미국인 매력적인 여성).
DEFAULT_CHARACTER = ModelSpec(
    age="early 20s",
    gender="female",
    look=(
        "an attractive American woman with Western features, naturally pretty aspirational "
        "beauty-influencer look, effortless minimal-makeup glam, warm approachable vibe"
    ),
)

_PROMPT = (
    "Define the on-camera creator/model for a vertical short-form beauty ad.\n"
    "Brief: {brief}\nProduct: {product}\n{ref}\n"
    "Rules: If the reference describes a person, MATCH that person (same gender, age range, "
    "ethnicity/nationality, look). Otherwise infer a fitting creator from the brief. If still "
    "unspecified, default to an attractive early-20s American (Western) woman. The person is an "
    "attractive, camera-ready beauty influencer (not a plain everyday person).\n"
    'Output raw JSON only (no markdown, no prose): '
    '{{"age": str, "gender": str, "look": str}}. '
    "The look field must include nationality/ethnicity and attractiveness cues."
)


def _extract_json(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


def _from_subject(subject: Subject) -> ModelSpec:
    """레퍼런스 인물 묘사를 그대로 캐릭터로 옮긴다(LLM 없이 쓰는 결정론 경로).

    인종·피부톤·헤어·착장까지 실어 레퍼런스 인물을 최대한 반영한다(정체성 보존).
    """
    look_bits = [
        subject.ethnicity,
        f"{subject.skin_tone} skin" if subject.skin_tone else None,
        subject.hair,
        subject.look,
        subject.wardrobe,
        "attractive beauty influencer look",
    ]
    return ModelSpec(
        age=subject.age_range or DEFAULT_CHARACTER.age,
        gender=subject.gender or DEFAULT_CHARACTER.gender,
        look=", ".join(b for b in look_bits if b) or DEFAULT_CHARACTER.look,
    )


def derive_character(
    brief: str,
    product: ProductSpec,
    reference_subject: Subject | None,
    text_client: TextClient | None,
) -> ModelSpec:
    """브리프·레퍼런스 인물로 캐릭터를 도출한다. LLM 우선, 실패/부재 시 결정론 폴백."""
    ref_person = reference_subject if (reference_subject and reference_subject.present) else None
    ref_hint = ""
    if ref_person is not None:
        reference_subject = ref_person
        ref_hint = (
            "Reference on-screen person (MATCH their identity): "
            f"gender={reference_subject.gender or 'unknown'}, "
            f"age={reference_subject.age_range or 'unknown'}, "
            f"ethnicity={reference_subject.ethnicity or 'unknown'}, "
            f"skin_tone={reference_subject.skin_tone or 'unknown'}, "
            f"hair={reference_subject.hair or 'unknown'}, "
            f"look={reference_subject.look or 'unknown'}, "
            f"wardrobe={reference_subject.wardrobe or 'unknown'}."
        )

    def _fallback() -> ModelSpec:
        return _from_subject(ref_person) if ref_person is not None else DEFAULT_CHARACTER.model_copy()

    if text_client is None:
        return _fallback()  # LLM 없으면 레퍼런스 인물 반영, 없으면 기본값

    try:
        raw = text_client.complete(
            _PROMPT.format(brief=brief, product=product.name, ref=ref_hint), temperature=0.7
        )
        data = json.loads(_extract_json(raw))
        look = str(data.get("look") or "").strip()
        if not look:
            raise ValueError("empty look")
        return ModelSpec(
            age=str(data.get("age") or DEFAULT_CHARACTER.age),
            gender=str(data.get("gender") or DEFAULT_CHARACTER.gender),
            look=look,
        )
    except Exception:
        return _fallback()
