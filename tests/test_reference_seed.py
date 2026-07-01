"""reference_seed의 결정론 매핑 테스트(외부 호출 없음)."""

from reel_gen_agent.analysis.profile import Voice
from reel_gen_agent.generate.reference_seed import _delivery_from


class _VP:
    """_delivery_from은 vp.voice만 본다. 최소 스텁으로 voice만 채운다."""

    def __init__(self, voice: Voice) -> None:
        self.voice = voice


def test_delivery_none_when_no_voice():
    assert _delivery_from(_VP(Voice(present=False))) == "none"


def test_delivery_voiceover_when_offscreen_narration():
    assert _delivery_from(_VP(Voice(present=True, on_camera=False))) == "voiceover"


def test_delivery_on_camera_when_person_talks_to_camera():
    # 레퍼런스 인물이 카메라 보고 말하면 생성도 온카메라 발화로 재현한다(하드코딩 X).
    assert _delivery_from(_VP(Voice(present=True, on_camera=True))) == "on_camera"
