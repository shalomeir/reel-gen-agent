"""캐릭터 노드: 입력·레퍼런스에서 등장 인물(ModelSpec)을 도출한다.

원칙(사용자 지시): 하드코딩하지 않는다. 레퍼런스에 인물이 나오면 그 설정(성별·나이대·인종·
외모)을 최대한 가져오고, 없으면 브리프를 보고 LLM이 적합한 캐릭터를 정한다. 아무 단서가
없을 때의 기본값만 코드가 쥐고 있다: 매력적인 20대 초반 미국(서구) 여성.
"""

from __future__ import annotations

import json
import os

from ..analysis.profile import Subject
from .schema import ModelSpec, ProductSpec
from .text_client import TextClient

# 단서가 전혀 없을 때만 쓰는 기본 캐릭터. 인종/국적을 명시해 이미지 모델이 임의로 동양인 등으로
# 흐르지 않게 한다(사용자 지시: 기본은 20대 초반 미국인 매력적인 여성).
# 기본은 연예인/슈퍼모델 급 미모로 생성한다(사용자 지시). 단서 없을 때만 쓰는 기본값.
DEFAULT_CHARACTER = ModelSpec(
    age="early 20s",
    gender="female",
    look=(
        "an exceptionally attractive early-20s American woman with Western features — the kind of "
        "conventionally stunning, camera-magnetic face you see on a top viral beauty influencer / "
        "TikTok creator / A-list celebrity: model-tier flawless symmetrical features, big expressive "
        "eyes, radiant clear glowing complexion, glossy healthy hair, an aspirational head-turning "
        "'it-girl' look, effortless minimal-makeup glam, highly photogenic and charismatic on camera"
    ),
)

# 매력도는 '기본 편향'이다(강제 고정 아님). 브리프/레퍼런스가 다른 외모를 분명히 원하면 그걸 따른다.
_ATTRACTIVE = (
    "Default bias (override only if the brief clearly asks for a different look): make the creator "
    "exceptionally, conventionally attractive — a top viral beauty influencer / TikToker / "
    "celebrity-tier face: model-tier, flawless, magnetic and highly photogenic, the aspirational "
    "'it-girl/it-guy' look people find beautiful, not plain or average."
)

_PROMPT = (
    "Define the on-camera creator/model for a vertical short-form video ad.\n"
    "Brief: {brief}\nProduct: {product}\n{ref}\n"
    "Priority order (follow the most specific available): (1) If the reference describes a person, "
    "MATCH that person (same gender, age range, ethnicity/nationality, look). (2) Otherwise infer a "
    "fitting creator from the brief and product (e.g. a runner for running shoes, follow any stated "
    "gender/age/ethnicity/vibe). (3) ONLY if still unspecified, fall back to the default: an "
    f"exceptionally attractive early-20s American (Western) woman, top viral creator look.\n{_ATTRACTIVE}\n"
    'Output raw JSON only (no markdown, no prose): '
    '{{"age": str, "gender": str, "look": str}}. '
    "The look field includes nationality/ethnicity; add strong attractiveness cues only when the "
    "brief/reference does not specify a different look (do not override an explicit look with "
    "generic beauty cues)."
)


# 사용자가 준 캐릭터 참조 이미지를 인물 정체성으로 읽는 VLM 지시. 관측한 것만 채우고 default로
# 흐르지 말라고 못 박는다(성별·인종·나이대는 이 이미지에서 나온다).
_DESCRIBE_PROMPT = (
    "You are looking at a reference photo of a PERSON that a creator wants the on-camera model to "
    "resemble. Describe THIS person's real identity so a generator can create a similar-looking "
    "(not identical) model. Report ONLY what you actually observe in the photo — do not assume or "
    "fall back to any default. Fill: present=true (a person is shown), gender (as observed: female "
    "or male), age_range (e.g. 'early 20s', 'late 30s'), ethnicity (as observed, e.g. 'east asian', "
    "'white', 'black/african'), skin_tone (e.g. 'fair', 'medium tan', 'deep'), hair (length, color, "
    "style), look (one line on the face, features and overall vibe), wardrobe (what they are "
    "wearing). If the image clearly shows no identifiable person, set present=false."
)


def describe_character_image(image_path: str | None) -> Subject | None:
    """사용자가 준 캐릭터 참조 이미지를 VLM으로 읽어 Subject(인물 정체성)로 돌려준다.

    이 이미지는 그동안 image-to-image 참조로만 쓰였다. 그 인물의 성별·나이대·인종이 text
    LLM(derive_character)에 전달되지 않으면, 브리프에 성별을 안 적었을 때 캐릭터가 default(여성)로
    흘러 남성 참조를 줘도 여성이 생성되는 버그가 난다(관측). 그래서 참조 이미지를 먼저 서술해
    derive_character가 그 정체성을 매칭하게 한다. 백엔드가 없거나 실패하면 None(호출 측이 폴백).
    """
    if not image_path or not os.path.exists(image_path):
        return None
    from ..analysis.gemini_client import (
        generate_structured,
        make_client,
        resolve_model,
        select_backend,
    )

    selection = select_backend()
    if selection is None:
        return None
    try:
        from google.genai import types

        client = make_client(selection)
        mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
        with open(image_path, "rb") as fh:
            part = types.Part.from_bytes(data=fh.read(), mime_type=mime)
        result = generate_structured(
            client, types, resolve_model(None), [part, _DESCRIBE_PROMPT], Subject
        )
    except Exception:
        return None
    if result is not None and not result.present and (
        result.gender or result.look or result.ethnicity
    ):
        # VLM이 성별·외모를 읽었는데 present만 빠뜨렸으면 인물이 있는 것으로 본다(present 누락 방어).
        # 아무것도 못 읽었으면 인물 없음(present=false)을 그대로 존중한다.
        result.present = True
    return result


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
    # 레퍼런스 인물은 input이다. 그 인물의 실제 외모(인종·피부톤·헤어·룩·착장)를 그대로 옮기고,
    # 미모를 supermodel급으로 덧칠하지 않는다(사용자 지시: 하드코딩 금지, input 우선). 매력도
    # 기본 편향은 단서가 아예 없을 때 쓰는 DEFAULT_CHARACTER에만 있다.
    look_bits = [
        subject.ethnicity,
        f"{subject.skin_tone} skin" if subject.skin_tone else None,
        subject.hair,
        subject.look,
        subject.wardrobe,
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
