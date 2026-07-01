"""에셋 생성 헬퍼: 캐릭터/제품 레퍼런스 이미지를 나노바나나로 만든다.

각 에셋은 해당 노드(character/product)에서 그 단계에 생성한다(별도 통합 assets 노드 없음).
공통 이미지 코드는 여기서 재사용한다. 캐릭터는 **정면 레퍼런스 시트**(얼굴 일관성 근거,
중립 배경 - 환경은 컷별 스틸에서 입힌다). 제품은 카탈로그 히어로 + 풀 패키지 샷. 이 이미지들이
execute의 컷별 스틸 생성에서 reference·폴백으로 쓰인다. 클라이언트가 없거나 실패하면 에셋 없이 진행.
"""

from __future__ import annotations

from pathlib import Path

from .image_client import ImageClient
from .schema import (
    AssetView,
    CharacterProfile,
    ModelSpec,
    ProductProfile,
    ProductSpec,
    ReelProfile,
)

# 패키지 텍스트 처리 지시. 실제 제품 사진을 참조로 쓰면 잔글씨까지 따라 그리다 뭉개진다.
# 그래서 처음부터 크고 또렷한 브랜드명 한 개만 남기고, 성분·용량 같은 자잘한 인쇄 문구는
# 그리지 말고 그 자리를 깔끔히 비우게 한다(뭉갠 가짜 텍스트 방지).
_PACKAGE_TEXT_RULE = (
    " Keep the packaging shape, colors and layout faithful, and render only the single most "
    "prominent brand name if it is large and clearly legible; OMIT all small print, ingredient "
    "lists, weights and fine sub-copy - leave those areas clean and blank rather than drawing tiny "
    "unreadable or garbled text."
)


def _palette_phrase(palette: list[str] | None) -> str:
    """팔레트를 이미지 프롬프트용 색 그레이딩 지시로 바꾼다(hex를 그대로 안 따르므로 강조)."""
    if not palette:
        return ""
    tones = ", ".join(palette[:5])
    return f" Color grading and overall tones in this palette: {tones}. Match this mood and warmth."


def _character_prompt(
    character: ModelSpec, palette: list[str] | None, has_reference: bool = False
) -> str:
    # 인물 정체성·매력도는 character 노드가 이미 정했다(look). 여기서 다시 하드코딩하지 않고
    # 그 결정을 쓴다. 레퍼런스 시트라 배경은 중립(깨끗한 실내)으로 — 실제 환경은 컷별 스틸이 입힌다.
    look = character.look or "an exceptionally attractive early-20s woman, aspirational influencer look"
    age = character.age or "early 20s"
    gender = character.gender or "female"
    # 입력 인물 이미지를 가깝게 따르되, 얼굴을 '살짝만' 바꾼다(완전히 다른 사람 X). 레퍼런스의
    # 이목구비·헤어·분위기·그리고 높은 미모를 그대로 유지하고, 미세한 특징만 조정해 픽셀 단위
    # 동일 복제만 피한다. 이렇게 해야 원하는 룩과 매력도가 함께 살고, 완전 별인으로 만들다 평범해
    # 지는 것을 막는다(사용자 지시: 살짝만 바꿔라).
    ref_clause = (
        "Follow the reference image CLOSELY: keep the same overall face, features, hair, coloring, "
        "styling and — most importantly — her high level of beauty. Make only a SLIGHT variation "
        "(subtly adjust a few minor features) so the result is not a pixel-perfect identity copy of "
        "the exact same individual, while still clearly reading as the same look and the same "
        "(or higher) attractiveness. Do NOT turn her into a noticeably different-looking or less "
        "attractive person; stay close and keep her stunning. "
        if has_reference
        else ""
    )
    # 매력도는 광고 성패를 가르는 요소라 강하게 못 박는다(사용자 지시: 셀럽/톱인플루언서급).
    beauty = (
        "She must be breathtakingly, exceptionally beautiful: a supermodel / top viral beauty-"
        "influencer / A-list-celebrity-tier face — flawless and strikingly symmetrical features, "
        "big luminous eyes, sculpted bone structure, radiant perfect skin, glossy healthy hair, "
        "the aspirational 'it-girl' look that stops the scroll. Absolutely not plain, ordinary or "
        "average-looking; maximize conventional beauty and on-camera magnetism."
    )
    return (
        f"Photorealistic vertical 9:16 front-facing upper-body portrait of {look}, "
        f"{age} {gender}. {ref_clause}{beauty} "
        "Looking straight at the camera, natural soft indoor lighting, clean neutral "
        "bright background, authentic UGC selfie aesthetic, natural skin texture with balanced "
        "lighting (avoid excessive dewy sheen or greasy highlights), clean and bright. "
        "A fictional person, not a real or identifiable individual." + _palette_phrase(palette)
    )


def _product_prompt(product: ProductSpec, palette: list[str] | None) -> str:
    # 시각 정체성(카테고리·제형·용기·색·특징)을 실어 히어로가 곧 컷마다 재현할 기준이 되게 한다.
    from .product import product_identity

    return (
        f"Studio e-commerce catalog photo of {product_identity(product)}. "
        "Clean seamless off-white background, soft even studio lighting, single hero "
        "product centered, subtle reflection, sharp focus, high detail, no caption overlay, "
        "no hands, no human, vertical 9:16 framing, photorealistic."
        + _PACKAGE_TEXT_RULE + _palette_phrase(palette)
    )


def _product_packaging_prompt(product: ProductSpec, palette: list[str] | None) -> str:
    """제품 박스·풀 패키지 카탈로그 컷. 정면 히어로 외에 개봉/박스 상태를 함께 잡는다."""
    from .product import product_identity

    return (
        f"Studio e-commerce catalog photo of {product_identity(product)} with its full packaging: "
        "the retail box and the product bottle/tube shown together. "
        "Clean seamless off-white background, soft even studio lighting, three-quarter angle, "
        "subtle reflection, sharp focus, high detail, no caption overlay, no hands, no human, "
        "vertical 9:16 framing, photorealistic." + _PACKAGE_TEXT_RULE + _palette_phrase(palette)
    )


def build_character_asset(
    character: ModelSpec,
    image_client: ImageClient | None,
    out_dir: str,
    palette: list[str] | None = None,
    refs: list[str] | None = None,
) -> CharacterProfile:
    """캐릭터 정면 레퍼런스 시트를 만들어 CharacterProfile로 돌려준다(character 노드에서 호출).

    refs가 있으면(입력 인물 이미지) image-to-image로 그 룩을 참고해 만든다. 정체성 복제가 아니라
    헤어·스타일·피부톤·분위기만 따르는 '룩 레퍼런스'로 쓰고 새 가상 인물을 만든다(RAI 안전).
    이미지 경로는 run 폴더 기준 상대명(character.png)으로 저장해 ReelProfile을 이식 가능하게 둔다.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    refs = [r for r in (refs or []) if r]
    prompt = _character_prompt(character, palette, has_reference=bool(refs))
    rel: str | None = None
    if image_client is not None:
        try:
            image_client.generate(prompt, refs, str(out / "character.png"), hero=True)
            rel = "character.png"
        except Exception:
            rel = None
    return CharacterProfile(name=character.name, prompt_used=prompt, key_shot_image=rel)


def build_key_visual(
    profile: ReelProfile,
    image_client: ImageClient | None,
    out_dir: str,
    character_image: str | None = None,
    product_image: str | None = None,
) -> str | None:
    """영상을 대표하는 키 비주얼 한 장을 만든다(plan 확정 시). 상대 파일명(key_visual.png) 반환.

    캐릭터·제품 에셋을 레퍼런스로 넣고, ReelProfile의 스토리보드·스타일·환경을 종합해 "이 영상이
    어떤 느낌으로 만들어질지"를 잘 보여주는 대표 순간(대개 중간 세그먼트의 제품 사용 장면)을
    그린다. 커버로도, 중간 세그먼트 앵커 스틸로도 재활용 가능. 클라이언트 없거나 실패하면 None.
    """
    if image_client is None:
        return None
    panels = profile.storyboard.panels
    # 대표 순간: 스토리보드 중간 패널(제품 사용/변화 지점)을 고른다. 없으면 제품 정체성만으로.
    mid = panels[len(panels) // 2] if panels else None
    from .product import FACE_MASK_CLARITY, SOLO_PERSON, product_identity

    global_prompt = profile.storyboard.global_prompt or ""
    moment = (mid.action if (mid and mid.action) else None) or (
        f"the creator using {product_identity(profile.product)}, natural glowing result"
    )
    palette = profile.style.palette or []
    prompt = (
        f"{global_prompt}. Key representative hero frame of the whole short video: {moment}. "
        "A single striking vertical 9:16 still that best captures the video's overall mood, styling "
        f"and story at a glance (cover/keyframe). {SOLO_PERSON} {FACE_MASK_CLARITY} "
        "Photorealistic, no on-screen text or captions." + _palette_phrase(palette)
    )
    refs = [r for r in (character_image, product_image) if r]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    try:
        image_client.generate(prompt, refs, str(out / "key_visual.png"), hero=True)
        return "key_visual.png"
    except Exception:
        return None


def build_product_asset(
    product: ProductSpec,
    image_client: ImageClient | None,
    out_dir: str,
    palette: list[str] | None = None,
    refs: list[str] | None = None,
) -> ProductProfile:
    """제품 히어로 + 풀 패키지 샷을 만들어 ProductProfile로 돌려준다(product 노드에서 호출).

    refs가 있으면(입력 제품 이미지) 그 형태·색·라벨을 참고해 같은 제품으로 렌더한다.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    refs = [r for r in (refs or []) if r]
    prod_prompt = _product_prompt(product, palette)
    pkg_prompt = _product_packaging_prompt(product, palette)
    prod_rel: str | None = None
    views: list[AssetView] = []
    if image_client is not None:
        try:
            image_client.generate(prod_prompt, refs, str(out / "product.png"), hero=True)
            prod_rel = "product.png"
        except Exception:
            prod_rel = None
        try:
            image_client.generate(pkg_prompt, refs, str(out / "product_packaging.png"), hero=True)
            views.append(
                AssetView(name="packaging", image="product_packaging.png", satisfied=True)
            )
        except Exception:
            pass
    return ProductProfile(
        name=product.name, prompt_used=prod_prompt, hero_image=prod_rel, views=views
    )
