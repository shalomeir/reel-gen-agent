"""나레이션 TTS 백엔드. voiceover 전달일 때 캐릭터 음색의 나레이션을 만든다.

1차 ElevenLabs([ai-model-records.md] §6). 키(`ELEVENLABS_API_KEY`)가 있을 때만 동작하고,
실패하면 호출 측이 voice 없이(무음/BGM만) 진행하게 예외를 올린다. 음색은 캐릭터 설정에서
유도한 voice 설명을 참고한다.
"""

from __future__ import annotations

import os

# 기본 보이스: ElevenLabs 공개 프리셋(젊은 여성, Rachel). ELEVENLABS_VOICE_ID로 덮어쓴다.
_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


class ElevenLabsVoiceClient:
    def __init__(self, voice_id: str | None = None, model: str | None = None) -> None:
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or _DEFAULT_VOICE_ID
        self.model = model or os.environ.get("ELEVENLABS_MODEL") or "eleven_multilingual_v2"

    def synthesize(self, text: str, voice_desc: str, out_path: str) -> str:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
        audio = client.text_to_speech.convert(
            voice_id=self.voice_id,
            model_id=self.model,
            text=text,
            output_format="mp3_44100_128",
        )
        with open(out_path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)
        return out_path
