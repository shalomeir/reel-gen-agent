"""캐릭터 노드 테스트. LLM 없이(결정론 경로) 레퍼런스 반영/기본값을 검증한다."""

from reel_gen_agent.analysis.profile import Subject
from reel_gen_agent.generate.character import DEFAULT_CHARACTER, derive_character
from reel_gen_agent.generate.schema import ProductSpec

_PRODUCT = ProductSpec(name="glow serum")


def test_default_is_attractive_early20s_american_woman_without_llm():
    # 단서 없고 LLM 없으면 기본값(20대 초반 매력적 미국 여성). 하드코딩 동양인 아님.
    c = derive_character("morning skincare reel", _PRODUCT, None, text_client=None)
    assert c.gender == "female"
    assert "20s" in (c.age or "")
    assert "american" in (c.look or "").lower()


def test_reference_person_is_reflected_without_llm():
    # 레퍼런스에 인물이 있으면 그 인종·피부톤을 캐릭터에 반영한다(입력 반영).
    subj = Subject(
        present=True,
        gender="female",
        age_range="late 20s",
        ethnicity="black/african",
        skin_tone="deep",
        hair="long dark curly",
    )
    c = derive_character("skincare reel", _PRODUCT, subj, text_client=None)
    assert c.gender == "female"
    assert c.age == "late 20s"
    assert "black/african" in (c.look or "")
    assert "deep skin" in (c.look or "")


def test_absent_reference_person_falls_back_to_default():
    # 레퍼런스는 있지만 인물이 없으면(present=False) 기본값으로 간다.
    c = derive_character("b-roll product reel", _PRODUCT, Subject(present=False), text_client=None)
    assert c.look == DEFAULT_CHARACTER.look
