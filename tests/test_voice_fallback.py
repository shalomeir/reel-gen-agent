"""voice 재료 폴백 순서: 1차 ElevenLabs, 폴백 Google TTS. 외부 호출은 몽키패치로 막는다.

계약: specs/ai-model-records.md §6. delivery=voiceover이고 대사가 있을 때만 생성한다.
"""

from reel_gen_agent.generate import materials
from reel_gen_agent.generate.backends import gemini_tts, voice_tts
from reel_gen_agent.generate.schema import (
    NarrationLine,
    NarrationSpec,
    Objective,
    ProductSpec,
    ReelProfile,
)


def _profile(delivery="voiceover", lines=("hi there",)):
    return ReelProfile(
        objective=Objective(goal="demo"),
        product=ProductSpec(name="serum"),
        narration=NarrationSpec(
            delivery=delivery,
            lines=[NarrationLine(panel_index=i, text=t) for i, t in enumerate(lines)],
        ),
    )


def _stub(monkeypatch, cls, tag, calls):
    def synth(self, text, voice_desc, out_path):
        calls.append(tag)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(tag)
        return out_path

    monkeypatch.setattr(cls, "synthesize", synth)


def test_no_voice_when_delivery_not_voiceover(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    assert materials._build_voice(_profile(delivery="none"), str(tmp_path)) is None


def test_no_voice_when_no_lines(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    assert materials._build_voice(_profile(lines=()), str(tmp_path)) is None


def test_elevenlabs_is_primary_when_key_present(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    calls: list[str] = []
    _stub(monkeypatch, voice_tts.ElevenLabsVoiceClient, "eleven", calls)
    _stub(monkeypatch, gemini_tts.GeminiTTSVoiceClient, "gemini", calls)
    out = materials._build_voice(_profile(), str(tmp_path))
    assert out is not None and calls == ["eleven"]


def test_falls_back_to_gemini_when_no_elevenlabs_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    calls: list[str] = []
    _stub(monkeypatch, gemini_tts.GeminiTTSVoiceClient, "gemini", calls)
    out = materials._build_voice(_profile(), str(tmp_path))
    assert out is not None and calls == ["gemini"]


def test_falls_back_to_gemini_when_elevenlabs_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x")
    calls: list[str] = []

    def boom(self, text, voice_desc, out_path):
        calls.append("eleven")
        raise RuntimeError("blocked")

    monkeypatch.setattr(voice_tts.ElevenLabsVoiceClient, "synthesize", boom)
    _stub(monkeypatch, gemini_tts.GeminiTTSVoiceClient, "gemini", calls)
    out = materials._build_voice(_profile(), str(tmp_path))
    assert out is not None and calls == ["eleven", "gemini"]
