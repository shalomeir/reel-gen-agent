"""제품 소스 보강: 제품 URL 하나만으로도 정확한 제품 카탈로그를 만들 수 있게 하는 앞단.

제품 노드는 이 에이전트가 프로덕션에 쓰일 수준인지를 가르는 가장 중요한 노드다. 제품을 텍스트
이름만으로 짐작하지 않고, 실제 판매 페이지를 근거로 삼는다:

1. `collect_materials(url)`  - Firecrawl로 판매 페이지를 스크래핑해 제목·본문(설명·특징)과 제품
   사진 여러 장(백업 자료)을 모은다. 제품 사진은 og:image와 같은 이미지 코드를 공유하는 URL만
   추려 아이콘·배너·추천상품을 걸러낸다.
2. `extract_product(...)`     - 모은 제품 사진들을 VLM(Gemini)으로 함께 분석하고 본문 텍스트를
   근거로 대, 카테고리·제형·용기·색·식별 특징·USP·가능 행동을 채운 ProductSpec을 뽑는다. 즉
   "주요 이미지 분석 + 제품 정보 반영"을 한 번의 멀티모달 호출로 근거 있게 수행한다.

여기서 나온 ProductSpec과 실제 제품 이미지(참조용)는 제품 히어로/패키지 렌더뿐 아니라 훅·
스토리보드 노드로도 흘러 컷마다 같은 제품이 흔들리지 않게 하는 앵커가 된다. 스크래핑/분석이
실패하면 조용히 비워, 호출 측이 기존 텍스트 경로(derive_product)로 폴백하게 한다. 브랜드명은
코드에 하드코딩하지 않는다 - 무슨 URL이 들어오든 그 페이지를 읽을 뿐이다.
"""

from __future__ import annotations

import io
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from .schema import ProductSpec

# 근거로 LLM에 대는 본문 발췌 상한. 판매 페이지 마크다운은 내비게이션·리뷰로 길어지므로 앞부분을
# 넉넉히 자른다(제품 제목·설명이 대개 앞쪽에 있고, VLM 이미지가 시각 정체성을 보완한다).
_WEB_CONTEXT_LIMIT = 14000
# 다운로드할 제품 사진 최대 장수(여러 각도 = 백업 자료). 너무 많으면 VLM 비용만 늘어난다.
_MAX_IMAGES = 5
_IMG_MD = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
# 제품 사진이 아닌 자산(로고·아이콘·배너·결제수단)을 URL 경로로 거른다.
_NON_PRODUCT = ("/cms/", "/icons/", "/banners/", "/icon/", ".svg", "/flags/")
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) reel-gen-agent/1.0"


@dataclass
class ProductMaterials:
    """제품 URL에서 모은 근거 자료 묶음."""

    title: str | None
    web_context: str  # LLM에 댈 근거 텍스트(제목 + 본문 발췌)
    image_paths: list[str] = field(default_factory=list)  # 내려받은 제품 사진(참조·분석용)
    source_url: str | None = None


class _ProductExtract(BaseModel):
    """VLM 구조화 출력 스키마. ProductSpec으로 옮기기 위한 평평한 형태(union 타입 회피)."""

    name: str = ""
    category: str = ""
    form: str = ""
    packaging_desc: str = ""
    colors: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    affordances: list[str] = Field(default_factory=list)
    usp: str = ""
    spec: str = ""
    visual_summary: str = ""
    benefits: list[str] = Field(default_factory=list)
    key_ingredients: list[str] = Field(default_factory=list)
    how_to_use: str = ""
    description: str = ""


def _image_code(url: str) -> str | None:
    """이미지 CDN 경로에서 제품 식별 코드를 뽑는다(예: images/bdo/bdo36106/... -> bdo36106).

    같은 제품의 여러 각도 사진은 이 코드를 공유한다. 이 코드로 필터하면 판매 페이지의 잡다한
    이미지(아이콘·배너·추천상품)에서 대상 제품 사진만 정확히 골라낸다.
    """
    m = re.search(r"/images/[^/]+/([^/]+)/", url)
    return m.group(1) if m else None


def _product_image_urls(markdown: str, og_image: str | None) -> list[str]:
    """마크다운에서 대상 제품의 사진 URL만 순서대로 추린다.

    og:image의 이미지 코드를 기준으로, 같은 코드를 공유하는 사진만 남긴다. og가 없거나 코드를
    못 얻으면 비제품 자산만 걸러 앞쪽 몇 장을 쓴다(사이트 무관 폴백).
    """
    found = _IMG_MD.findall(markdown)
    ordered = ([og_image] if og_image else []) + found
    code = _image_code(og_image) if og_image else None
    picks: list[str] = []
    seen: set[str] = set()
    for url in ordered:
        if not url or url in seen:
            continue
        if any(bad in url for bad in _NON_PRODUCT):
            continue
        if code is not None and _image_code(url) != code:
            continue
        seen.add(url)
        picks.append(url)
    return picks[:_MAX_IMAGES]


def _download_image(url: str, dest: Path) -> str | None:
    """이미지를 내려받아 JPEG로 정규화 저장한다(webp/png 혼재를 통일). 실패하면 None."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (신뢰 URL, 사용자 제공)
            data = resp.read()
        from PIL import Image

        Image.open(io.BytesIO(data)).convert("RGB").save(dest, format="JPEG", quality=92)
        return str(dest)
    except Exception:
        return None


def _scrape(url: str) -> tuple[str | None, str, str | None] | None:
    """Firecrawl로 페이지를 스크래핑해 (title, markdown, og_image)를 돌려준다. 실패하면 None."""
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        return None
    try:
        from firecrawl import Firecrawl

        fc = Firecrawl(api_key=key)
        doc = fc.scrape(url, formats=["markdown"], only_main_content=True, timeout=60000)
    except Exception:
        return None
    markdown = getattr(doc, "markdown", None) or ""
    meta = getattr(doc, "metadata", None)
    title = getattr(meta, "title", None) if meta is not None else None
    og = getattr(meta, "og_image", None) if meta is not None else None
    if not og:  # 일부 응답은 metadata를 dict로 준다
        og = meta.get("ogImage") if isinstance(meta, dict) else None
    if isinstance(og, list):
        og = og[0] if og else None
    if not markdown and not title:
        return None
    return title, markdown, og


def collect_materials(url: str, out_dir: str) -> ProductMaterials | None:
    """제품 URL에서 근거 자료(본문 + 제품 사진 다수)를 모은다. 스크래핑 불가면 None.

    제품 사진은 out_dir에 product_src_1.jpg ... 로 내려받는다(참조·VLM 분석용 백업 자료).
    """
    scraped = _scrape(url)
    if scraped is None:
        return None
    title, markdown, og = scraped
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    image_paths: list[str] = []
    for i, img_url in enumerate(_product_image_urls(markdown, og), start=1):
        saved = _download_image(img_url, out / f"product_src_{i}.jpg")
        if saved:
            image_paths.append(saved)
    excerpt = markdown[:_WEB_CONTEXT_LIMIT]
    web_context = (
        f"SOURCE PRODUCT PAGE TITLE: {title or 'n/a'}\n\n"
        f"SOURCE PAGE CONTENT (excerpt, authoritative - extract the real product's facts from here):\n"
        f"{excerpt}"
    )
    return ProductMaterials(
        title=title, web_context=web_context, image_paths=image_paths, source_url=url
    )


_EXTRACT_PROMPT = (
    "You are analyzing a real product from its store page for a short-form product ad. Using BOTH the "
    "product photos shown and the page text below, fill an accurate spec so the SAME product can be "
    "rendered consistently across many cuts and referenced by the hook and storyboard. Ground every "
    "field in what you actually see/read - do not invent. Use the real product's own name. Do NOT "
    "reproduce brand logos or on-package marketing text in later renders (that is handled downstream); "
    "here just report the product truthfully.\n\n"
    "{web}\n\n"
    "Report the product EXACTLY as it truly is - do NOT assume it is a beauty cosmetic or nudge it "
    "toward skincare/makeup. It may be a cosmetic, but it may just as well be apparel, a bag, shoes, "
    "eyewear, an accessory, a supplement, a device or a home item; classify it by what it actually "
    "is. Fill: name (the product's real name), category (its true type, e.g. 'glow serum', 'leather "
    "tote bag', 'running shoe', 'collagen supplement', 'sunglasses'), form (material/texture/type "
    "appropriate to it, e.g. 'lightweight watery serum', 'soft grained leather', 'knit upper'), "
    "packaging_desc (container or how it is presented, e.g. 'frosted glass bottle with dropper', "
    "'kraft gift box', 'bare item, no packaging'), colors (2-4 dominant product/packaging colors), "
    "key_features (2-4 distinctive PHYSICAL/VISUAL cues that identify THIS product - shape, container "
    "type, material/finish, color scheme; NOT brand names, logos, or printed marketing text), "
    "affordances (3-6 concrete on-camera actions it enables, fit them to THIS product - e.g. 'apply "
    "to skin', 'worn on the shoulder', 'laced up', 'texture close-up'), usp (single most compelling "
    "one-liner benefit), spec (size/count/format), visual_summary (one line on how it looks on "
    "camera).\n"
    "ALSO capture the product's SUBSTANCE from the page text so the ad copy is not thin (ground "
    "each in the text, do not invent): benefits (2-5 concrete user benefits or claims the page "
    "makes, e.g. '72-hour hydration', 'refines the look of pores'), key_ingredients (up to 5 hero "
    "ingredients or, for non-cosmetics, key materials/components), how_to_use (one short line on "
    "how it is used/applied/worn), description (1-2 factual sentences summarizing what the product "
    "is and does, drawn from the page - factual, not marketing hype). Leave any field empty if the "
    "page does not state it."
)


def _to_spec(ex: _ProductExtract, fallback_name: str) -> ProductSpec:
    """VLM 추출 결과를 ProductSpec으로 옮긴다(빈 값은 None/빈 리스트로)."""
    return ProductSpec(
        name=(ex.name.strip() or fallback_name or "product"),
        usp=ex.usp.strip() or None,
        spec=ex.spec.strip() or None,
        packaging_desc=ex.packaging_desc.strip() or None,
        category=ex.category.strip() or None,
        form=ex.form.strip() or None,
        colors=[c.strip() for c in ex.colors if c.strip()],
        key_features=[k.strip() for k in ex.key_features if k.strip()],
        affordances=[a.strip() for a in ex.affordances if a.strip()],
        benefits=[b.strip() for b in ex.benefits if b.strip()],
        key_ingredients=[i.strip() for i in ex.key_ingredients if i.strip()],
        how_to_use=ex.how_to_use.strip() or None,
        # description이 비면 visual_summary라도 실어 제품 근거를 남긴다(예전엔 통째로 버려졌다).
        description=(ex.description.strip() or ex.visual_summary.strip() or None),
    )


def extract_product(materials: ProductMaterials, fallback_name: str = "product") -> ProductSpec | None:
    """모은 제품 사진 + 본문을 한 번의 멀티모달 호출로 분석해 ProductSpec을 뽑는다.

    이미지 분석과 텍스트 근거를 함께 대 정확도를 높인다. 백엔드 자격이 없거나 호출이 실패하면
    None을 돌려주고, 호출 측은 텍스트 전용 경로(derive_product, web_context 사용)로 폴백한다.
    """
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
        contents: list = []
        for path in materials.image_paths:
            if os.path.exists(path):
                with open(path, "rb") as fh:
                    contents.append(types.Part.from_bytes(data=fh.read(), mime_type="image/jpeg"))
        contents.append(_EXTRACT_PROMPT.format(web=materials.web_context))
        result = generate_structured(
            client, types, resolve_model(None), contents, _ProductExtract
        )
    except Exception:
        return None
    if result is None:
        return None
    return _to_spec(result, fallback_name)
