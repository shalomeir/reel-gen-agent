"""캐릭터 노드 테스트. LLM 없이(결정론 경로) 레퍼런스 반영/기본값을 검증한다."""

from reel_gen_agent.analysis.profile import Subject
from reel_gen_agent.generate.asset_bible import _character_prompt
from reel_gen_agent.generate.character import (
    DEFAULT_CHARACTER,
    derive_character,
    describe_character_image,
)
from reel_gen_agent.generate.schema import ModelSpec, ProductSpec

_PRODUCT = ProductSpec(name="glow serum")

# 프롬프트 렌더가 하드코딩으로 다시 주입하면 안 되는 여성 표지어. 이 단어들은 오직 character.look
# (입력·default 편향에서 도출)에서만 흘러들어와야 한다.
_HARDCODED_FEMININE = (" she ", " her ", "it-girl", "supermodel")


def _has_any(text: str, words) -> bool:
    low = f" {text.lower()} "
    return any(w in low for w in words)


def test_male_character_prompt_has_no_hardcoded_feminine_override():
    # 명시적 남성 캐릭터인데 렌더가 여성 언어(she/her/it-girl/supermodel)를 하드코딩으로 박으면
    # 이미지 모델이 그 문구에 끌려가 여성으로 뒤집힌다(관측된 버그). 렌더는 look/gender를 충실히
    # 옮길 뿐 성별 내용을 다시 주입하면 안 된다(사용자 지시: 하드코딩 금지, input 우선).
    male = ModelSpec(
        age="early 30s",
        gender="male",
        look="a strikingly handsome Korean man, sharp jawline, black leather jacket",
    )
    prompt = _character_prompt(male, palette=None, has_reference=True)
    assert not _has_any(prompt, _HARDCODED_FEMININE), prompt
    assert "male" in prompt.lower()
    # 남성 look이 그대로 렌더에 실려야 한다(input 우선).
    assert "handsome korean man" in prompt.lower()


def test_render_is_faithful_to_look_without_reinjecting_beauty():
    # 미모/성별 '내용'은 look 한 곳에서만 온다. look에 없는 미모 문구를 렌더가 지어내면 안 된다.
    plain = ModelSpec(age="40s", gender="female", look="an ordinary middle-aged woman, natural look")
    prompt = _character_prompt(plain, palette=None, has_reference=False)
    assert "ordinary middle-aged woman" in prompt.lower()
    # 렌더가 "supermodel / it-girl"을 강제 주입해 평범한 요청을 미인으로 덮지 않는다.
    assert not _has_any(prompt, ("it-girl", "supermodel")), prompt


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


def test_male_reference_person_produces_male_character():
    # 남성 참조 인물이 오면 남성 캐릭터가 나와야 한다(default 여성으로 덮지 않는다). 이게
    # 캐릭터 참조 이미지→Subject→derive_character 경로가 남성 요청을 지키는 핵심 회귀 방지다.
    subj = Subject(
        present=True,
        gender="male",
        age_range="early 30s",
        ethnicity="east asian",
        hair="short black",
        look="a strikingly handsome man, sharp jawline",
    )
    c = derive_character("skincare reel", _PRODUCT, subj, text_client=None)
    assert c.gender == "male"
    assert c.age == "early 30s"
    assert "east asian" in (c.look or "")
    # 강제 미모("supermodel-tier")를 덧칠하지 않고 참조 인물 서술만 반영한다.
    assert "supermodel" not in (c.look or "").lower()


def test_describe_character_image_is_graceful_without_backend():
    # 백엔드 없거나 경로가 없으면 None을 돌려 호출 측이 폴백하게 한다(크래시 금지).
    assert describe_character_image(None) is None
    assert describe_character_image("/nonexistent/path/to/image.png") is None
