"""제품 분석 노드: 브리프(+레퍼런스 제품 힌트)에서 제품 스펙을 LLM이 추출한다.

스토리보드·후크·제품 이미지가 제대로 되려면 제품을 이해해야 한다. 이름만 들고 가지 말고,
카테고리·제형·용기·USP·가능한 사용 행동(affordances)을 뽑아 다른 노드가 문맥으로 쓴다.
레퍼런스 제품의 시각 특성(카테고리/제형/용기/색)은 힌트로만 참고한다(사용자 제품을 대체 X).
"""

from __future__ import annotations

import json

from ..analysis.profile import Product
from .schema import ProductSpec
from .text_client import TextClient

_PROMPT = (
    "Analyze the advertised product for a short-form beauty ad and fill its spec. Infer sensible "
    "details from the name/brief; keep it realistic for this category. Do NOT invent a brand.\n"
    "Product name/brief: {name}\nExtra brief: {brief}\n{ref}\n"
    'Output raw JSON only (no markdown, no prose): '
    '{{"name": str, "category": str, "usp": str, "packaging_desc": str, '
    '"affordances": [str, ...]}}. '
    "category e.g. 'glow serum', 'cushion foundation'. usp = the single most compelling one-liner. "
    "packaging_desc = the container look (e.g. 'frosted glass dropper bottle'). affordances = "
    "3-6 concrete on-camera actions the product enables (e.g. 'dropper onto hand', 'pat into "
    "cheeks', 'texture close-up', 'mist over face')."
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
    return f"Reference product visual traits (style hint only, keep the user's product): {hint}." if hint else ""


def derive_product(
    name: str,
    brief: str,
    reference_product: Product | None,
    text_client: TextClient | None,
) -> ProductSpec:
    """브리프·레퍼런스로 ProductSpec을 채운다. LLM 우선, 실패/부재 시 이름만 있는 기본."""
    base = ProductSpec(name=name or "product")
    if text_client is None:
        return base
    try:
        raw = text_client.complete(
            _PROMPT.format(name=name, brief=brief, ref=_ref_hint(reference_product)),
            temperature=0.6,
        )
        data = json.loads(_extract_json(raw))
        affordances = [str(a).strip() for a in (data.get("affordances") or []) if str(a).strip()]
        return ProductSpec(
            name=str(data.get("name") or name or "product"),
            usp=(str(data.get("usp")).strip() or None) if data.get("usp") else None,
            spec=base.spec,
            packaging_desc=(str(data.get("packaging_desc")).strip() or None)
            if data.get("packaging_desc")
            else None,
            affordances=affordances,
        )
    except Exception:
        return base
