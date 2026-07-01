"""asset_bible 노드: 캐릭터·제품 에셋 이미지를 나노바나나로 생성한다.

캐릭터는 **정면샷**으로 만든다(멀티샷을 이어붙일 때 얼굴 일관성의 근거, specs/trd.md
"기본 제작 포맷"). 제품은 카탈로그 히어로 샷. 이 두 이미지가 execute의 컷별 스틸 생성에서
reference·폴백으로 쓰인다. 이미지 클라이언트가 없거나 실패하면 에셋 없이 진행한다.
"""

from __future__ import annotations

from pathlib import Path

from .image_client import ImageClient
from .schema import (
    AssetBible,
    AssetView,
    CharacterProfile,
    EnvironmentSpec,
    ModelSpec,
    ProductProfile,
    ProductSpec,
)


def _palette_phrase(palette: list[str] | None) -> str:
    """팔레트를 이미지 프롬프트용 색 그레이딩 지시로 바꾼다(hex를 그대로 안 따르므로 강조)."""
    if not palette:
        return ""
    tones = ", ".join(palette[:5])
    return f" Color grading and overall tones in this palette: {tones}. Match this mood and warmth."


# 인물은 평범한 일반인이 아니라 매력적인 뷰티 인플루언서/틱톡커여야 한다(사용자 지시).
# 일반인처럼 밋밋하게 나오는 걸 막는 매력·인플루언서 디스크립터를 프롬프트에 항상 얹는다.
_INFLUENCER_DESC = (
    "She is a highly attractive, camera-ready beauty influencer and TikTok/YouTube creator "
    "(not a plain everyday person): striking, magnetic good looks, healthy clear skin with "
    "natural realistic texture and visible pores (matte-to-soft finish, not oily, wet or overly "
    "shiny, no plastic glossy sheen), polished on-trend hair and subtle glam, expressive "
    "charismatic eyes, confident aspirational creator vibe, photogenic and scroll-stopping"
)


def _character_prompt(
    character: ModelSpec, environment: EnvironmentSpec, palette: list[str] | None
) -> str:
    look = character.look or "a naturally pretty early-20s woman, effortless natural look"
    age = character.age or "early 20s"
    gender = character.gender or "female"
    loc = environment.location or "the creator's own bedroom, indoor"
    return (
        f"Photorealistic vertical 9:16 front-facing upper-body portrait of {look}, "
        f"{age} {gender}. {_INFLUENCER_DESC}. Looking straight at the camera, natural soft "
        f"indoor lighting, {loc} in the background, authentic UGC selfie aesthetic, natural skin "
        "texture with balanced lighting (avoid excessive dewy sheen or greasy highlights), clean "
        "and bright. A fictional person, not a real or identifiable individual."
        + _palette_phrase(palette)
    )


def _product_prompt(product: ProductSpec, palette: list[str] | None) -> str:
    packaging = product.packaging_desc or "as described"
    return (
        f"Studio e-commerce catalog photo of {product.name}. Packaging: {packaging}. "
        "Clean seamless off-white background, soft even studio lighting, single hero "
        "product centered, subtle reflection, sharp focus, high detail, no text overlay, "
        "no hands, no human, vertical 9:16 framing, photorealistic." + _palette_phrase(palette)
    )


def _product_packaging_prompt(product: ProductSpec, palette: list[str] | None) -> str:
    """제품 박스·풀 패키지 카탈로그 컷. 정면 히어로 외에 개봉/박스 상태를 함께 잡는다."""
    packaging = product.packaging_desc or "as described"
    return (
        f"Studio e-commerce catalog photo of {product.name} with its full packaging: "
        f"the retail box and the product bottle/tube shown together. Packaging: {packaging}. "
        "Clean seamless off-white background, soft even studio lighting, three-quarter angle, "
        "subtle reflection, sharp focus, high detail, no text overlay, no hands, no human, "
        "vertical 9:16 framing, photorealistic." + _palette_phrase(palette)
    )


def build_asset_bible(
    character: ModelSpec,
    product: ProductSpec,
    environment: EnvironmentSpec,
    image_client: ImageClient | None,
    out_dir: str,
    palette: list[str] | None = None,
) -> AssetBible:
    """캐릭터 정면샷 + 제품 히어로샷을 만들어 AssetBible을 채운다(상대 파일명으로 기록).

    이미지 경로는 run 폴더 기준 상대명(character.png/product.png)으로 저장해 ReelProfile을
    이식 가능하게 둔다. execute가 폴더 기준으로 절대경로를 해소한다.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    char_prompt = _character_prompt(character, environment, palette)
    prod_prompt = _product_prompt(product, palette)
    pkg_prompt = _product_packaging_prompt(product, palette)

    char_rel: str | None = None
    prod_rel: str | None = None
    views: list[AssetView] = []
    if image_client is not None:
        try:
            # 캐릭터 설정 샷·제품 카탈로그 모두 히어로 스틸(4K Pro)로 만든다(ai-model-records.md §3).
            image_client.generate(char_prompt, [], str(out / "character.png"), hero=True)
            char_rel = "character.png"
        except Exception:
            char_rel = None
        try:
            image_client.generate(prod_prompt, [], str(out / "product.png"), hero=True)
            prod_rel = "product.png"
        except Exception:
            prod_rel = None
        try:
            # 풀 카탈로그: 박스·패키지 뷰도 plan 단계에서 함께 생성한다(사용자 지시).
            image_client.generate(pkg_prompt, [], str(out / "product_packaging.png"), hero=True)
            views.append(
                AssetView(name="packaging", image="product_packaging.png", satisfied=True)
            )
        except Exception:
            pass

    return AssetBible(
        character=CharacterProfile(
            name=character.name, prompt_used=char_prompt, key_shot_image=char_rel
        ),
        product=ProductProfile(
            name=product.name, prompt_used=prod_prompt, hero_image=prod_rel, views=views
        ),
        environment=environment,
    )
