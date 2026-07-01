"""제품 분석·정체성 결정론 테스트."""

from __future__ import annotations

from reel_gen_agent.analysis.profile import Product
from reel_gen_agent.generate.product import derive_product, product_identity
from reel_gen_agent.generate.schema import ProductSpec


def test_product_identity_includes_visual_traits_not_just_name():
    p = ProductSpec(
        name="Glow Serum",
        category="glow serum",
        form="jelly-to-mist",
        packaging_desc="frosted spray bottle with white pump",
        colors=["pink", "clear"],
        key_features=["white pump", "frosted bottle"],
    )
    ident = product_identity(p)
    for token in ("Glow Serum", "glow serum", "jelly-to-mist", "frosted", "pink", "white pump"):
        assert token in ident


def test_product_identity_degrades_to_name_only():
    assert product_identity(ProductSpec(name="Mystery")) == "Mystery"


def test_derive_product_without_llm_adopts_reference_visual_traits():
    # LLM이 없으면 레퍼런스 제품의 시각 특성을 그대로 정체성으로 가져온다(브랜드만 다르게).
    ref = Product(
        present=True, category="serum mist", form="jelly-to-mist",
        packaging="frosted spray bottle", colors=["pink", "clear"],
        text_visible=["SomeBrand"],
    )
    spec = derive_product("My Glow Serum", "morning routine", ref, text_client=None)
    assert spec.name == "My Glow Serum"  # 사용자 제품명 유지
    assert spec.category == "serum mist"
    assert spec.form == "jelly-to-mist"
    assert "pink" in spec.colors
    # 브랜드/라벨 문구는 정체성에 넣지 않는다.
    assert "SomeBrand" not in product_identity(spec)


class _FakeTC:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def complete(self, prompt: str, temperature: float = 0.6) -> str:
        return self._payload


def test_derive_product_llm_fills_visual_identity():
    fake = _FakeTC(
        '{"name":"My Serum","category":"glow serum","form":"lightweight oil",'
        '"packaging_desc":"amber dropper bottle","colors":["amber","gold"],'
        '"key_features":["glass dropper","amber glass"],"usp":"instant glow",'
        '"affordances":["dropper onto hand","pat into cheeks"]}'
    )
    spec = derive_product("My Serum", "brief", None, text_client=fake)
    assert spec.category == "glow serum"
    assert spec.form == "lightweight oil"
    assert "amber" in spec.colors
    assert "glass dropper" in spec.key_features
    assert spec.affordances  # 사용 행동도 유지
