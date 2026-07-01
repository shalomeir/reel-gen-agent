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


class _FakeText:
    """derive_music LLM 경로용 가짜 텍스트 클라이언트(고정 JSON 반환)."""

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def complete(self, prompt: str, temperature: float = 0.7) -> str:
        return self._payload


def test_llm_decides_sfx_and_bgm_none():
    # 음악 노드가 SFX/베드 유무를 결정하고 MusicSpec에 실어야 한다.
    fake = _FakeText(
        '{"style":"asmr ambient","mood":"calm","type":"texture","dynamics":"flat",'
        '"prominence":"background","vocal":false,"bgm":"none","sfx":true}'
    )
    m = derive_music("asmr skincare", _PRODUCT, ["sensorial"], None, text_client=fake)
    assert m.sfx is True
    assert m.bgm == "none"


def test_music_is_always_instrumental_bed():
    # 보컬은 시도하지 않는다(Lyria 3 한계 + 사용자 지시): LLM이 보컬을 원해도 항상 인스트루멘털.
    fake = _FakeText(
        '{"style":"indie pop","mood":"upbeat","type":"song","dynamics":"build",'
        '"prominence":"prominent","vocal":true,"bgm":"bed","sfx":false}'
    )
    m = derive_music("vibey grwm", _PRODUCT, ["fun"], None, text_client=fake)
    assert m.vocal is False


def test_llm_dynamics_detail_carried_through():
    # 강약(에너지 컨투어) 세부 서술을 MusicSpec에 실어 Lyria 프롬프트로 전달한다.
    fake = _FakeText(
        '{"style":"deep house","mood":"premium","type":"bed","instrumentation":"sub bass, pads",'
        '"dynamics_detail":"soft intro, subtle lift toward the end","dynamics":"build",'
        '"prominence":"background","bgm":"bed","sfx":false}'
    )
    m = derive_music("clean beauty", _PRODUCT, ["premium"], None, text_client=fake)
    assert m.dynamics_detail == "soft intro, subtle lift toward the end"
    assert m.instrumentation == "sub bass, pads"
