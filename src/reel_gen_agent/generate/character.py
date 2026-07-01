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
# 기본은 확실한 미인(매력적)으로 생성한다(사용자 지시). 단서 없을 때만 쓰는 기본값.
DEFAULT_CHARACTER = ModelSpec(
    age="early 20s",
    gender="female",
    look=(
        "a strikingly beautiful, gorgeous early-20s American woman with Western features, "
        "stunning aspirational beauty-influencer looks, flawless symmetrical features, radiant "
        "clear complexion, effortless minimal-makeup glam, warm magnetic vibe"
    ),
)

# 매력도는 '기본 편향'이다(강제 고정 아님). 브리프/레퍼런스가 다른 외모를 분명히 원하면 그걸 따른다.
_ATTRACTIVE = (
    "Default bias (override only if the brief clearly asks for a different look): make the person "
    "strikingly attractive and beautiful — a gorgeous, scroll-stopping beauty influencer."
)

_PROMPT = (
    "Define the on-camera creator/model for a vertical short-form beauty ad.\n"
    "Brief: {brief}\nProduct: {product}\n{ref}\n"
    "Rules: If the reference describes a person, MATCH that person (same gender, age range, "
    "ethnicity/nationality, look). Otherwise infer a fitting creator from the brief. If still "
    f"unspecified, default to a strikingly beautiful early-20s American (Western) woman.\n{_ATTRACTIVE}\n"
    'Output raw JSON only (no markdown, no prose): '
    '{{"age": str, "gender": str, "look": str}}. '
    "The look field must include nationality/ethnicity and attractiveness/beauty cues."
)


def character_brief(character: ModelSpec) -> str:
    """캐릭터를 한 줄 요약한다. 다른 노드(대사·후크·음악·톤)가 문맥으로 공유한다.

    캐릭터는 영상의 주인공이다. "이 캐릭터라면 어떤 대사·톤·페이싱일까"를 각 노드가 판단하도록
    이 요약을 프롬프트에 함께 넣는다.
    """
    bits = [character.age, character.gender, character.look]
    return ", ".join(b for b in bits if b) or "an attractive early-20s American beauty creator"


def voice_persona(character: ModelSpec) -> str:
    """캐릭터에서 voice 성향을 한 줄로 뽑는다(성별·나이·분위기). TTS 보이스 선택·연기 지시에 쓴다.

    voice는 캐릭터에 맞아야 개성이 산다(사용자 지시). 시각(look) 전체가 아니라 목소리에
    영향 주는 축(성별·나이·기운/톤)만 추린다.
    """
    bits = [character.gender, character.age, character.look]
    return ", ".join(b for b in bits if b) or "female, early 20s, warm energetic American"


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
        # LLM 없는 폴백: 레퍼런스 인물을 충실히 반영하고 가벼운 '세련된 인플루언서' 톤만 더한다
        # (강제 미인 고정 아님).
        "polished beauty-influencer look",
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
        # LLM 결과를 그대로 존중한다. 매력도는 프롬프트의 '기본 편향'으로만 유도하고, 브리프가
        # 평범한/특정 외모를 원해 LLM이 그렇게 냈으면 코드가 미인으로 덮어쓰지 않는다(의도 존중).
        return ModelSpec(
            age=str(data.get("age") or DEFAULT_CHARACTER.age),
            gender=str(data.get("gender") or DEFAULT_CHARACTER.gender),
            look=look,
        )
    except Exception:
        return _fallback()
