"""음악 노드 테스트. LLM 없이(결정론 경로) 하드코딩 장르가 안 나오는지 검증한다."""

from reel_gen_agent.generate.music import derive_music
from reel_gen_agent.generate.schema import MusicSpec, ProductSpec

_PRODUCT = ProductSpec(name="glow serum")


def test_no_llm_no_reference_has_no_hardcoded_genre():
    # LLM도 레퍼런스도 없으면 장르를 지어내지 않는다(무드는 톤에서만 온다).
    m = derive_music("morning skincare reel", _PRODUCT, ["fresh"], None, text_client=None)
    assert m.style is None  # "pop" 같은 장르 하드코딩 없음
    assert m.mood == "fresh"


def test_no_llm_uses_reference_music():
    # LLM이 없으면 레퍼런스 음악을 그대로 쓴다(임의 장르로 덮어쓰지 않음).
    ref = MusicSpec(mood="dreamy", style="lo-fi", dynamics="build", tempo="120 bpm")
    m = derive_music("skincare reel", _PRODUCT, ["fresh"], ref, text_client=None)
    assert m.style == "lo-fi"
    assert m.tempo == "120 bpm"
