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


class AssetGenerationError(ValueError):
    """이미지 클라이언트가 있는데도 필수 에셋 이미지를 하나도 만들지 못한 경우.

    클라이언트가 없을 때(테스트·--no-images)의 '에셋 없이 진행'과 구분한다: 그건 정상 워킹
    스켈레톤이지만, 이 오류는 실제 생성 실패다. 조용히 넘겨 에셋 없는 ReelProfile을 쓰면
    execute의 stills가 "앵커 스틸 없음"으로 뒤늦게 터진다. 발생 지점(plan)에서 진짜 사유로
    멈추기 위한 예외다. ValueError를 상속해 chat의 계획 실패 처리 경로에 자연히 걸린다.
    """


# 패키지 텍스트 처리 지시. 실제 제품 사진을 참조로 쓰면 잔글씨까지 따라 그리다 뭉개진다.
# 그래서 크고 또렷한 글씨(브랜드명 등)는 원본 그대로 살리고, 성분·용량 같은 자잘한 인쇄 문구만
# 지워 그 자리를 깔끔히 비운다. 원본에 없는 글씨나 placeholder/번역 문구는 절대 지어내지 않는다.
_PACKAGE_TEXT_RULE = (
    " Keep the packaging shape, colors and layout faithful to the real product. Preserve any large, "
    "prominent text exactly as it appears on the real product (e.g. the main brand or product name); "
    "only OMIT the small print - ingredient lists, weights and fine sub-copy - and leave those areas "
    "clean and blank rather than drawing tiny unreadable text. Never invent, translate or add any "
    "text, label or placeholder wording that is not actually on the real product."
)


def _palette_phrase(palette: list[str] | None) -> str:
    """팔레트를 이미지 프롬프트용 색 그레이딩 지시로 바꾼다(hex를 그대로 안 따르므로 강조)."""
    if not palette:
        return ""
    tones = ", ".join(palette[:5])
    return f" Color grading and overall tones in this palette: {tones}. Match this palette's mood."


def _character_prompt(
    character: ModelSpec, palette: list[str] | None, has_reference: bool = False
) -> str:
    """캐릭터 정면 레퍼런스 시트 프롬프트. character 노드가 정한 값(look/age/gender)을 그대로
    렌더할 뿐, 성별·미모 같은 '내용'을 여기서 다시 하드코딩하지 않는다.

    미모/매력도 편향은 입력이 특정하지 않을 때만 쓰는 default로 이미 character.look에 담겨 있다
    (DEFAULT_CHARACTER, 그리고 LLM 도출 프롬프트가 그렇게 유도). 여기서 "She must be a
    supermodel it-girl" 같은 문구를 다시 주입하면 사용자가 요청한 성별·외모를 덮어써 버그가 난다
    (남성 요청→여성 생성). 그래서 이 함수는 render 전용이고, 레퍼런스 충실도 지시도 성별 표지 없이
    성 중립 대명사로 쓴다. 배경만 중립(깨끗한 실내)으로 둔다 — 실제 환경은 컷별 스틸이 입힌다.
    """
    look = character.look or "an attractive early-20s creator"
    age = character.age or "early 20s"
    gender = character.gender or "female"
    # 입력 인물 이미지가 있으면 그 룩·매력도를 가깝게 따르되, 완전 동일 복제만 피하도록 '살짝만'
    # 바꾼다. 성별을 못 박지 않으려 대명사는 성 중립(this person/them)으로 둔다.
    ref_clause = (
        "Follow the reference image CLOSELY: keep the same overall face, features, hair, coloring, "
        "styling and the same high level of attractiveness. Make only a SLIGHT variation (subtly "
        "adjust a few minor features) so the result is not a pixel-perfect identity copy of the "
        "exact same individual, while still clearly reading as the same look and the same (or "
        "higher) attractiveness. Do NOT turn this person into a noticeably different-looking or "
        "less attractive one; stay close and keep them striking. "
        if has_reference
        else ""
    )
    return (
        f"Photorealistic vertical 9:16 front-facing upper-body portrait of {look}, "
        f"{age} {gender}. {ref_clause}"
        "Looking straight at the camera, natural soft indoor lighting, clean neutral "
        "bright background, a clean neutral reference portrait (scene styling is applied later "
        "per shot). A fictional person, not a real or identifiable individual." + _palette_phrase(palette)
    )


# 입력 제품 이미지가 있을 때, 텍스트 서술이 제품을 다른 물건으로 끌고 가지 않게 원본 충실을 못 박는다.
_PRODUCT_FAITHFUL = (
    " Match the reference product image EXACTLY: the same product, with the same shape, container, "
    "material, proportions and colors. Do NOT substitute, restyle or turn it into a different-looking "
    "product; reproduce the real one as faithfully as possible."
)


def _product_prompt(
    product: ProductSpec, palette: list[str] | None, has_reference: bool = False
) -> str:
    # 시각 정체성(카테고리·제형·용기·색·특징)을 실어 히어로가 곧 컷마다 재현할 기준이 되게 한다.
    from .product import product_identity

    faithful = _PRODUCT_FAITHFUL if has_reference else ""
    return (
        f"Studio e-commerce catalog photo of {product_identity(product)}. "
        "Clean seamless off-white background, soft even studio lighting, single hero "
        "product centered, subtle reflection, sharp focus, high detail, no caption overlay, "
        "no hands, no human, vertical 9:16 framing, photorealistic."
        + faithful + _PACKAGE_TEXT_RULE + _palette_phrase(palette)
    )


def _product_packaging_prompt(
    product: ProductSpec, palette: list[str] | None, has_reference: bool = False
) -> str:
    """제품 박스·풀 패키지 카탈로그 컷. 정면 히어로 외에 개봉/박스 상태를 함께 잡는다."""
    from .product import product_identity

    faithful = _PRODUCT_FAITHFUL if has_reference else ""
    return (
        f"Studio e-commerce catalog photo of {product_identity(product)} with its full packaging: "
        "the retail box and the product bottle/tube shown together. "
        "Clean seamless off-white background, soft even studio lighting, three-quarter angle, "
        "subtle reflection, sharp focus, high detail, no caption overlay, no hands, no human, "
        "vertical 9:16 framing, photorealistic."
        + faithful + _PACKAGE_TEXT_RULE + _palette_phrase(palette)
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
    그린다. 커버와 분위기 참조로 쓰며, 세그먼트 앵커 스틸은 각 세그먼트 첫 패널 설정으로
    별도 생성한다. 클라이언트 없거나 실패하면 None.
    """
    if image_client is None:
        return None
    panels = profile.storyboard.panels
    # 대표 순간: 스토리보드 중간 패널(제품 사용/변화 지점)을 고른다. 없으면 제품 정체성만으로.
    mid = panels[len(panels) // 2] if panels else None
    from .product import SOLO_PERSON, product_identity

    global_prompt = profile.storyboard.global_prompt or ""
    moment = (mid.action if (mid and mid.action) else None) or (
        f"the creator using {product_identity(profile.product)}, natural glowing result"
    )
    palette = profile.style.palette or []
    prompt = (
        f"{global_prompt}. Key representative hero frame of the whole short video: {moment}. "
        "A single striking vertical 9:16 still that best captures the video's overall mood, styling "
        f"and story at a glance (cover/keyframe). {SOLO_PERSON} "
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
    prod_prompt = _product_prompt(product, palette, has_reference=bool(refs))
    pkg_prompt = _product_packaging_prompt(product, palette, has_reference=bool(refs))
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
