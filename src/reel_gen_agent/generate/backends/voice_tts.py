"""나레이션 TTS 백엔드. voiceover 전달일 때 캐릭터 음색의 나레이션을 만든다.

1차 ElevenLabs([ai-model-records.md] §6). 키(`ELEVENLABS_API_KEY`)가 있을 때만 동작하고,
실패하면 호출 측이 voice 없이(무음/BGM만) 진행하게 예외를 올린다.

무료 플랜은 라이브러리 보이스(예: Rachel)를 API로 못 쓰므로, 기본값을 계정에서 접근
가능한 여성 프리메이드 보이스(Sarah)로 두고, 그마저 막히면 계정 보이스 목록에서 자동으로
고른다. 기본 캐릭터가 20대 초중반 여성이라 여성 보이스를 우선한다.
"""

from __future__ import annotations

import os

# 계정 접근 가능한 여성 프리메이드 보이스(Sarah). ELEVENLABS_VOICE_ID로 덮어쓴다.
_DEFAULT_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
_FEMALE_HINTS = ("sarah", "alice", "laura", "matilda", "jessica", "lily", "rachel")


class ElevenLabsVoiceClient:
    def __init__(self, voice_id: str | None = None, model: str | None = None) -> None:
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or _DEFAULT_VOICE_ID
        self.model = model or os.environ.get("ELEVENLABS_MODEL") or "eleven_multilingual_v2"

    def _pick_account_voice(self, client) -> str | None:
        """계정에서 쓸 수 있는 보이스 중 여성 우선으로 하나 고른다."""
        try:
            voices = client.voices.get_all().voices
        except Exception:
            return None
        for v in voices:
            if any(h in (v.name or "").lower() for h in _FEMALE_HINTS):
                return v.voice_id
        return voices[0].voice_id if voices else None

    def _convert(self, client, voice_id: str, text: str, out_path: str) -> str:
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id=self.model,
            text=text,
            output_format="mp3_44100_128",
        )
        with open(out_path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)
        return out_path

    def synthesize(self, text: str, voice_desc: str, out_path: str) -> str:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
        try:
            return self._convert(client, self.voice_id, text, out_path)
        except Exception:
            # 지정 보이스가 막히면(무료 플랜 라이브러리 보이스 등) 계정 보이스로 재시도.
            alt = self._pick_account_voice(client)
            if not alt:
                raise
            return self._convert(client, alt, text, out_path)
