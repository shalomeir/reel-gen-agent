"""제품 알맹이(효능·성분·사용법) 캡처와 카피용 요약(product_brief) 검증.

배경: 예전엔 URL 추출이 시각 정체성 + usp 한 줄만 담아 hook·스토리·나레이션 카피가 빈약했다.
이제 benefits/key_ingredients/how_to_use/description을 함께 담고 product_brief로 카피에 흘린다.
"""

from __future__ import annotations

from reel_gen_agent.generate.product import product_brief
from reel_gen_agent.generate.product_source import _ProductExtract, _to_spec
from reel_gen_agent.generate.schema import ProductSpec


def test_product_brief_includes_substance():
    p = ProductSpec(
        name="Biodance Serum",
        category="collagen serum",
        usp="fast hydration",
        benefits=["refines pores", "boosts elasticity"],
        key_ingredients=["low-molecular collagen", "peptides"],
        how_to_use="pump onto clean skin",
        description="A collagen peptide serum for smoother, firmer skin.",
    )
    brief = product_brief(p)
    for token in (
        "Biodance Serum",
        "refines pores",
        "low-molecular collagen",
        "pump onto clean skin",
        "smoother, firmer skin",
    ):
        assert token in brief


def test_product_brief_thin_product_is_safe():
    assert product_brief(ProductSpec(name="X")) == "X"


def test_to_spec_carries_substance_fields():
    ex = _ProductExtract(
        name="P",
        benefits=["b1", "b2"],
        key_ingredients=["i1"],
        how_to_use="use it",
        description="what it is",
    )
    spec = _to_spec(ex, "fallback")
    assert spec.benefits == ["b1", "b2"]
    assert spec.key_ingredients == ["i1"]
    assert spec.how_to_use == "use it"
    assert spec.description == "what it is"


def test_to_spec_description_falls_back_to_visual_summary():
    # description이 비면 예전에 통째로 버려지던 visual_summary라도 실어 제품 근거를 남긴다.
    ex = _ProductExtract(name="P", description="", visual_summary="looks glossy on camera")
    spec = _to_spec(ex, "fallback")
    assert spec.description == "looks glossy on camera"
