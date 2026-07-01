"""제품 분석 노드: 브리프(+레퍼런스 제품 힌트)에서 제품 스펙을 LLM이 추출한다.

스토리보드·후크·제품 이미지가 제대로 되려면 제품을 이해해야 한다. 이름만 들고 가지 말고,
카테고리·제형·용기·색·식별 특징·USP·가능한 사용 행동(affordances)을 뽑아 다른 노드가 쓴다.

제품 시각 정체성(카테고리/제형/용기/색/특징)은 execute의 모든 생성 단계에 일관 주입돼 컷마다
제품이 흔들리지 않게 하는 앵커다(`product_identity`). 사용자 지시대로 "브랜드만 다르고 제품
자체는 거의 같게": 레퍼런스 제품이 있으면 그 형태 정체성을 최대한 따르되, 브랜드명/라벨
문구는 복제하지 않는다(사용자 제품명을 쓴다).
"""

from __future__ import annotations

import json

from ..analysis.profile import Product
from .schema import ProductSpec
from .text_client import TextClient

# 얼굴에 착용하는 시트/하이드로겔 마스크는 반드시 투명·반투명으로 렌더한다. 영상 모델(특히 Veo)이
# 따뜻한 조명 아래 투명 젤을 주황·갈색 끈적임으로 뭉개는 회귀를 막는다. 마스크가 아닌 제품엔 무해한
# 조건부 지시라 항상 붙여도 된다.
FACE_MASK_CLARITY = (
    "If a sheet mask or hydrogel mask is worn on the face, render it as a clean, clear, translucent, "
    "slightly milky-white gel sheet that conforms smoothly to the skin with neat eye, nose and mouth "
    "openings; it must NOT look orange, amber, yellow, brown, sticky, melting, slimy or goopy, even "
    "under warm lighting."
)
# 인물 중복(얼굴 2개) 버그 방지. 셀피/포트레이트 스틸과 영상 시작 프레임에 붙인다.
SOLO_PERSON = "Exactly ONE person in the frame, solo — no second person and no duplicate faces."

_PROMPT = (
    "Analyze the advertised product for a short-form beauty ad and fill its spec so the SAME "
    "product can be rendered consistently across many cuts. Infer sensible, realistic details from "
    "the name/brief. Use the user's product name. Do NOT invent or copy a brand name or on-package "
    "text.\n"
    "Product name/brief: {name}\nExtra brief: {brief}\n{web}{ref}\n"
    'Output raw JSON only (no markdown, no prose): '
    '{{"name": str, "category": str, "form": str, "packaging_desc": str, '
    '"colors": [str, ...], "key_features": [str, ...], "usp": str, "affordances": [str, ...]}}. '
    "category e.g. 'glow serum'. form = texture/type (e.g. 'lightweight jelly-to-mist'). "
    "packaging_desc = the container look (e.g. 'frosted glass spray bottle with white pump'). "
    "colors = 2-4 dominant product/packaging colors. key_features = 2-4 distinctive visual cues that "
    "identify this exact product (e.g. 'white pump', 'clear frosted bottle', 'rose-gold cap'). "
    "usp = the single most compelling one-liner. affordances = 3-6 concrete on-camera actions the "
    "product enables (e.g. 'mist over face', 'texture close-up'). "
    "If a reference product is given, MATCH its category/form/packaging/colors closely (same kind of "
    "product), only without its brand/label."
)


def _extract_json(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


def _ref_hint(ref: Product | None) -> str:
    if ref is None or not ref.present:
        return ""
    bits = [
        f"category={ref.category}" if ref.category else "",
        f"form={ref.form}" if ref.form else "",
        f"packaging={ref.packaging}" if ref.packaging else "",
        f"colors={', '.join(ref.colors)}" if ref.colors else "",
    ]
    hint = "; ".join(b for b in bits if b)
    return (
        f"Reference product to match visually (same kind of product, keep the user's name, do NOT "
        f"copy its brand/label): {hint}."
        if hint
        else ""
    )


def _from_reference(name: str, ref: Product | None) -> ProductSpec:
    """LLM 없이 쓰는 폴백. 레퍼런스 제품의 시각 특성을 그대로 정체성으로 옮긴다."""
    base = ProductSpec(name=name or "product")
    if ref is None or not ref.present:
        return base
    return ProductSpec(
        name=name or "product",
        category=ref.category,
        form=ref.form,
        packaging_desc=ref.packaging,
        colors=list(ref.colors),
    )


def product_identity(product: ProductSpec) -> str:
    """제품 시각 정체성 한 줄. 히어로 이미지·컷 스틸·영상 프롬프트가 공유해 컷마다 제품을 고정한다.

    브랜드/라벨 문구는 넣지 않는다(형태 정체성만). 값이 비면 그 조각은 생략한다.
    """
    bits: list[str] = [product.name] if product.name else []
    if product.category:
        bits.append(f"a {product.category}")
    if product.form:
        bits.append(product.form)
    if product.packaging_desc:
        bits.append(f"in a {product.packaging_desc}")
    if product.colors:
        bits.append(f"{', '.join(product.colors)} tones")
    if product.key_features:
        bits.append(f"distinctive: {', '.join(product.key_features)}")
    return ", ".join(bits) or (product.name or "the product")


def derive_product(
    name: str,
    brief: str,
    reference_product: Product | None,
    text_client: TextClient | None,
    web_context: str = "",
) -> ProductSpec:
    """브리프·레퍼런스로 ProductSpec을 채운다. LLM 우선, 실패/부재 시 레퍼런스 시각 특성 폴백.

    web_context가 있으면(제품 URL을 스크래핑한 판매 페이지 근거) 이름/브리프보다 우선해 실제
    제품의 카테고리·제형·용기·색·특징을 그 텍스트에서 뽑도록 프롬프트에 함께 댄다.
    """
    if text_client is None:
        return _from_reference(name, reference_product)
    web = f"{web_context.strip()}\n" if web_context.strip() else ""
    try:
        raw = text_client.complete(
            _PROMPT.format(
                name=name, brief=brief, web=web, ref=_ref_hint(reference_product)
            ),
            temperature=0.6,
        )
        data = json.loads(_extract_json(raw))

        def _list(key: str) -> list[str]:
            return [str(a).strip() for a in (data.get(key) or []) if str(a).strip()]

        ref = reference_product if (reference_product and reference_product.present) else None
        # LLM 값 우선, 비면 레퍼런스 시각 특성으로 메운다(제품을 최대한 레퍼런스와 같게).
        return ProductSpec(
            name=str(data.get("name") or name or "product"),
            usp=(str(data.get("usp")).strip() or None) if data.get("usp") else None,
            category=(str(data.get("category")).strip() or None) if data.get("category") else (ref.category if ref else None),
            form=(str(data.get("form")).strip() or None) if data.get("form") else (ref.form if ref else None),
            packaging_desc=(str(data.get("packaging_desc")).strip() or None)
            if data.get("packaging_desc")
            else (ref.packaging if ref else None),
            colors=_list("colors") or (list(ref.colors) if ref else []),
            key_features=_list("key_features"),
            affordances=_list("affordances"),
        )
    except Exception:
        return _from_reference(name, reference_product)
