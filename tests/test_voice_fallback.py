"""voice 재료: 비트 정렬 나레이션 + TTS 폴백(1차 ElevenLabs, 폴백 Gemini). 외부 호출은 몽키패치.

계약: specs/ai-model-records.md §6. delivery=voiceover이고 대사가 있을 때만, 각 라인을 패널
t_start에 맞춰 배치·합성한다.
"""

import wave

from reel_gen_agent.generate import materials
from reel_gen_agent.generate.backends import gemini_tts, voice_tts
from reel_gen_agent.generate.schema import (
    NarrationLine,
    NarrationSpec,
    Objective,
    ProductSpec,
    ReelProfile,
    Storyboard,
    StoryboardPanel,
)


def _write_wav(path: str, seconds: float = 0.5) -> str:
    """ffprobe가 길이를 읽을 수 있는 실제 무음 wav를 쓴다(스텁 TTS 산출물용)."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * int(22050 * seconds))
    return path


def _profile(delivery="voiceover", texts=("glow", "dewy")):
    panels = [
        StoryboardPanel(index=i, t_start=i * 1.0, t_end=i * 1.0 + 1.0) for i in range(len(texts))
    ]
    lines = [NarrationLine(panel_index=i, text=t) for i, t in enumerate(texts)]
    return ReelProfile(
        objective=Objective(goal="demo"),
        product=ProductSpec(name="serum"),
        storyboard=Storyboard(panels=panels),
        narration=NarrationSpec(delivery=delivery, lines=lines),
    )


def _stub_writes_wav(monkeypatch, cls, tag, calls):
    def synth(self, text, voice_desc, out_path):
        calls.append(tag)
        return _write_wav(out_path)

    monkeypatch.setattr(cls, "synthesize", synth)


def test_no_voice_when_delivery_not_voiceover(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    assert materials._build_voice(_profile(delivery="none"), str(tmp_path), 2.0) is None


def test_no_voice_when_no_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    assert materials._build_voice(_profile(texts=()), str(tmp_path), 2.0) is None


def test_elevenlabs_is_primary_when_key_present(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    calls: list[str] = []
    _stub_writes_wav(monkeypatch, voice_tts.ElevenLabsVoiceClient, "eleven", calls)
    _stub_writes_wav(monkeypatch, gemini_tts.GeminiTTSVoiceClient, "gemini", calls)
    out = materials._build_voice(_profile(), str(tmp_path), 2.0)
    assert out is not None
    assert set(calls) == {"eleven"}  # 두 라인 모두 ElevenLabs로


def test_falls_back_to_gemini_when_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    calls: list[str] = []
    _stub_writes_wav(monkeypatch, gemini_tts.GeminiTTSVoiceClient, "gemini", calls)
    out = materials._build_voice(_profile(), str(tmp_path), 2.0)
    assert out is not None
    assert set(calls) == {"gemini"}


def test_falls_back_to_gemini_when_elevenlabs_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    calls: list[str] = []

    def boom(self, text, voice_desc, out_path):
        calls.append("eleven")
        raise RuntimeError("blocked")

    monkeypatch.setattr(voice_tts.ElevenLabsVoiceClient, "synthesize", boom)
    _stub_writes_wav(monkeypatch, gemini_tts.GeminiTTSVoiceClient, "gemini", calls)
    out = materials._build_voice(_profile(texts=("glow",)), str(tmp_path), 2.0)
    assert out is not None
    assert calls == ["eleven", "gemini"]  # 라인마다 eleven 시도 후 gemini 폴백
