"""product_source 결정론 계층 테스트. 스크래핑/다운로드/VLM 등 외부 호출은 모킹한다."""

from __future__ import annotations

from pathlib import Path

from reel_gen_agent.generate import product_source as ps
from reel_gen_agent.generate.product_source import (
    ProductMaterials,
    _image_code,
    _product_image_urls,
    _ProductExtract,
    _to_spec,
    collect_materials,
    extract_product,
)

_OG = "https://cdn.example.com/image/upload/f_auto/images/bdo/bdo36106/s/31.jpg"
_MD = """
![](https://cdn.example.com/image/upload/f_auto/images/bdo/bdo36106/k/31.jpg)
![](https://cdn.example.com/image/upload/f_auto/images/bdo/bdo36106/r/32.jpg)
![logo](https://cdn.example.com/image/upload/f_auto/images/cms/icons/info/Lined_x.svg)
![banner](https://cdn.example.com/image/upload/f_auto/images/cms/banners/promo.jpg)
![other](https://cdn.example.com/image/upload/f_auto/images/ptt/ptt80359/u/73.jpg)
"""


def test_image_code_extracts_product_code():
    assert _image_code(_OG) == "bdo36106"
    assert _image_code("https://x/no/images/here.jpg") is None


def test_product_image_urls_keeps_only_target_product():
    urls = _product_image_urls(_MD, _OG)
    # og가 맨 앞, 같은 코드(bdo36106) 사진만. cms/아이콘/배너/다른 제품(ptt) 제외.
    assert urls[0] == _OG
    assert all("bdo36106" in u for u in urls)
    assert not any("/cms/" in u or ".svg" in u or "ptt80359" in u for u in urls)
    assert len(urls) == 3  # og + k/31 + r/32


def test_product_image_urls_fallback_without_og():
    # og가 없으면 코드 필터를 못 하니, 비제품 자산만 걸러 앞쪽을 쓴다.
    urls = _product_image_urls(_MD, None)
    assert not any("/cms/" in u or ".svg" in u for u in urls)
    assert any("bdo36106" in u for u in urls)


def test_to_spec_maps_and_blanks_empties():
    ex = _ProductExtract(
        name="Real Deep Mask",
        category="hydrogel sheet mask",
        form="clear jelly sheet",
        packaging_desc="flat foil sachet",
        colors=["dusty rose", "  "],
        key_features=["transparent sheet", ""],
        affordances=["peel from pouch"],
        usp="  ",
        spec="4 sheets",
    )
    spec = _to_spec(ex, fallback_name="fallback")
    assert spec.name == "Real Deep Mask"
    assert spec.category == "hydrogel sheet mask"
    assert spec.colors == ["dusty rose"]  # 공백 항목 제거
    assert spec.key_features == ["transparent sheet"]
    assert spec.usp is None  # 공백은 None
    assert spec.spec == "4 sheets"


def test_to_spec_uses_fallback_name_when_empty():
    spec = _to_spec(_ProductExtract(), fallback_name="my product")
    assert spec.name == "my product"


def test_collect_materials_downloads_and_builds_context(monkeypatch, tmp_path):
    monkeypatch.setattr(ps, "_scrape", lambda url: ("Real Deep Mask, 4 Sheets", _MD, _OG))

    def fake_download(url: str, dest: Path) -> str | None:
        dest.write_bytes(b"jpeg-bytes")
        return str(dest)

    monkeypatch.setattr(ps, "_download_image", fake_download)
    mats = collect_materials("https://shop.example/p/1", str(tmp_path))
    assert mats is not None
    assert mats.title == "Real Deep Mask, 4 Sheets"
    assert "SOURCE PRODUCT PAGE TITLE: Real Deep Mask" in mats.web_context
    assert len(mats.image_paths) == 3  # 대상 제품 사진만 내려받는다
    assert all(Path(p).exists() for p in mats.image_paths)


def test_collect_materials_none_when_scrape_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(ps, "_scrape", lambda url: None)
    assert collect_materials("https://shop.example/p/1", str(tmp_path)) is None


def test_extract_product_none_without_backend(monkeypatch):
    # 백엔드 자격이 없으면 None -> 호출 측이 텍스트 경로로 폴백한다.
    monkeypatch.setattr(
        "reel_gen_agent.analysis.gemini_client.select_backend", lambda *a, **k: None
    )
    mats = ProductMaterials(title="x", web_context="ctx", image_paths=[])
    assert extract_product(mats) is None
