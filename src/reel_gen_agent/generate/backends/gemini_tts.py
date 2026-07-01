"""나레이션 TTS 폴백 백엔드. ElevenLabs가 없거나 막힐 때만 쓴다([ai-model-records.md] §6).

Google TTS는 최신 Gemini 3.1 TTS preview(`GEMINI_TTS_MODEL`, 기본
`gemini-3.1-flash-tts-preview`)를 기준으로 한다. genai(Vertex 우선, GEMINI 폴백) 플러밍을
재사용한다. 응답은 PCM(24kHz 16-bit mono)이라 wav 헤더를 붙여 저장한다(ffmpeg가 읽어 mux).
"""

from __future__ import annotations

import base64
import os
import wave

# Gemini TTS 기본 응답 포맷(문서 기준): 24kHz, 16-bit, mono PCM.
_SAMPLE_RATE = 24000
_SAMPLE_WIDTH = 2
_CHANNELS = 1


# Gemini 프리빌트 보이스의 대략적 성별 매핑(캐릭터 페르소나에 맞춰 고른다).
_GEMINI_FEMALE_VOICES = ("Kore", "Aoede", "Leda")
_GEMINI_MALE_VOICES = ("Puck", "Charon", "Fenrir")


def _persona_gender(voice_desc: str) -> str:
    d = (voice_desc or "").lower()
    if any(w in d for w in ("male", " man", "guy", "boy", "masculine")) and (
        "female" not in d and "woman" not in d
    ):
        return "male"
    return "female"


class GeminiTTSVoiceClient:
    def __init__(self, model: str | None = None, voice: str | None = None) -> None:
        self.model = model or os.environ.get("GEMINI_TTS_MODEL") or "gemini-3.1-flash-tts-preview"
        # env로 고정하지 않으면 캐릭터 페르소나에 맞춰 synthesize에서 성별별로 고른다.
        self.voice = voice or os.environ.get("GEMINI_TTS_VOICE")

    def _pick_voice(self, voice_desc: str) -> str:
        if self.voice:
            return self.voice
        return (
            _GEMINI_MALE_VOICES[0]
            if _persona_gender(voice_desc) == "male"
            else _GEMINI_FEMALE_VOICES[0]
        )

    @staticmethod
    def _extract_pcm(response) -> bytes | None:
        for cand in getattr(response, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline else None
                if data:
                    return base64.b64decode(data) if isinstance(data, str) else data
        return None

    def synthesize(self, text: str, voice_desc: str, out_path: str) -> str:
        from google.genai import types

        from ...analysis.gemini_client import make_client, select_backend

        selection = select_backend()
        if selection is None:
            raise RuntimeError("Gemini TTS 자격 없음")
        client = make_client(selection)
        config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self._pick_voice(voice_desc)
                    )
                )
            ),
        )
        response = client.models.generate_content(model=self.model, contents=text, config=config)
        pcm = self._extract_pcm(response)
        if not pcm:
            raise RuntimeError("Gemini TTS 오디오 추출 실패")
        # out_path는 .wav로 쓴다(호출 측이 확장자를 맞춘다).
        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(_CHANNELS)
            wf.setsampwidth(_SAMPLE_WIDTH)
            wf.setframerate(_SAMPLE_RATE)
            wf.writeframes(pcm)
        return out_path
