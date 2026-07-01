"""_merge_gemini 병합 테스트(외부 호출 없이 결정론).

Gemini 지각 층이 채우는 인물(subject)·제품(product) 등이 VideoProfile로 제대로
병합되는지 본다. 정형 수치(밝기/bpm)는 보존되어야 한다.
"""

from reel_gen_agent.analysis.analyze import _merge_gemini
from reel_gen_agent.analysis.profile import (
    GeminiDescription,
    Product,
    Subject,
    VideoProfile,
)


def test_merge_carries_subject_and_product():
    profile = VideoProfile()
    profile.visual.brightness = 110.8  # 정형 수치(보존 확인용)

    desc = GeminiDescription(
        subject=Subject(
            present=True,
            gender="female",
            ethnicity="black/african",
            skin_tone="deep",
            hair="long dark curly",
            look="confident glam creator",
            wardrobe="cream knit top",
        ),
        product=Product(
            present=True,
            category="serum mist",
            form="jelly-to-mist",
            packaging="frosted spray bottle",
            colors=["soft pink", "clear"],
            text_visible=["Collagen"],
        ),
    )

    _merge_gemini(profile, desc)

    # 인물: 인종·피부톤이 관측대로 실린다(한국인으로 뭉개지지 않는다).
    assert profile.subject.present is True
    assert profile.subject.ethnicity == "black/african"
    assert profile.subject.skin_tone == "deep"
    assert profile.subject.hair == "long dark curly"
    # 제품: 카테고리·제형·용기·색이 실린다.
    assert profile.product.present is True
    assert profile.product.category == "serum mist"
    assert profile.product.form == "jelly-to-mist"
    assert profile.product.colors == ["soft pink", "clear"]
    # 정형 수치는 병합이 건드리지 않는다.
    assert profile.visual.brightness == 110.8


def test_merge_absent_subject_and_product_default_false():
    profile = VideoProfile()
    _merge_gemini(profile, GeminiDescription())
    assert profile.subject.present is False
    assert profile.product.present is False
