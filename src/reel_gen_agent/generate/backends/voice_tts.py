"""나레이션 TTS 백엔드. voiceover 전달일 때 캐릭터 음색의 나레이션을 만든다.

voice 1차는 언어(한국어/영어) 무관하게 ElevenLabs로 못박는다([ai-model-records.md] §6).
Google TTS보다 한 수 위라 기본으로 쓴다. 기본 모델은 `eleven_v3`로, 다국어 표현력이 가장
좋아 한국어·영어 나레이션 모두 이 모델을 쓴다. 키(`ELEVENLABS_API_KEY`)가 있을 때만
동작하고, 실패하면 호출 측이 voice 없이(무음/BGM만) 진행하게 예외를 올린다.

한국어는 voice 선택이 품질을 좌우한다. `eleven_v3`가 다국어라도 프리메이드 보이스마다
한국어 발음·억양 품질이 다르므로, 한국어에 적당한 여성 프리메이드 보이스 **Bella**를
기본으로 계정에서 이름으로 찾아 쓰고, `ELEVENLABS_VOICE_ID`로 다른 보이스에 고정할 수 있다.
Bella의 ID는 계정·라이브러리 버전마다 달라(같은 ID가 Sarah로 바뀌기도 함) 하드코딩하지 않고
이름으로 조회한다. 무료 플랜은 라이브러리 보이스를 API로 못 쓰므로, 지정 보이스가 막히면
계정에서 접근 가능한 여성 보이스로 자동 폴백한다. 기본 캐릭터가 20대 초중반 여성이라 여성
보이스를 우선한다.
"""

from __future__ import annotations

import os

# 한국어에 적당한 여성 프리메이드 보이스를 이름 우선순위로 고른다. Bella가 1순위다.
# ID가 계정/버전마다 달라(같은 ID가 Sarah로 바뀌기도) 이름으로 계정에서 찾는다.
_PREFERRED_VOICE_NAMES = (
    "bella",
    "sarah",
    "alice",
    "laura",
    "matilda",
    "jessica",
    "lily",
    "rachel",
)
# 이름으로 못 찾거나 계정 조회가 막힐 때 쓰는 접근 가능한 여성 프리메이드 보이스 ID(폴백).
_FALLBACK_VOICE_ID = "EXAVITQu4vr4xnSDxMaL"
# eleven_v3: 다국어 표현력이 가장 좋아 한국어·영어 나레이션 기본값([ai-model-records.md] §6).
_DEFAULT_MODEL = "eleven_v3"


class ElevenLabsVoiceClient:
    def __init__(self, voice_id: str | None = None, model: str | None = None) -> None:
        # 명시 지정이 없으면 synthesize에서 계정 보이스를 이름 우선순위(Bella 1순위)로 고른다.
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID")
        # env는 .env.example의 ELEVENLABS_TTS_MODEL을 정본으로, 구 이름도 함께 받는다.
        self.model = (
            model
            or os.environ.get("ELEVENLABS_TTS_MODEL")
            or os.environ.get("ELEVENLABS_MODEL")
            or _DEFAULT_MODEL
        )
        self.output_format = os.environ.get("ELEVENLABS_OUTPUT_FORMAT") or "mp3_44100_128"

    def _account_voices(self, client) -> list:
        """계정에서 쓸 수 있는 보이스 목록. 조회가 막히면 빈 목록."""
        try:
            return client.voices.get_all().voices
        except Exception:
            return []

    def _pick_account_voice(self, voices: list) -> str | None:
        """계정 보이스에서 선호 이름 우선순위(Bella 1순위)로 하나 고른다.

        선호 이름이 하나도 없으면 첫 번째 보이스를 쓴다.
        """
        for name in _PREFERRED_VOICE_NAMES:
            for v in voices:
                if name in (v.name or "").lower():
                    return v.voice_id
        return voices[0].voice_id if voices else None

    def _convert(self, client, voice_id: str, text: str, out_path: str) -> str:
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            model_id=self.model,
            text=text,
            output_format=self.output_format,
        )
        with open(out_path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)
        return out_path

    def synthesize(self, text: str, voice_desc: str, out_path: str) -> str:
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
        voices: list | None = None
        voice_id = self.voice_id
        if not voice_id:
            # 명시 지정이 없으면 계정에서 Bella 우선으로 고르고, 못 찾으면 폴백 ID.
            voices = self._account_voices(client)
            voice_id = self._pick_account_voice(voices) or _FALLBACK_VOICE_ID
        try:
            return self._convert(client, voice_id, text, out_path)
        except Exception:
            # 지정 보이스가 막히면(무료 플랜 라이브러리 보이스 등) 다른 계정 보이스로 재시도.
            if voices is None:
                voices = self._account_voices(client)
            alt = self._pick_account_voice(voices)
            if not alt or alt == voice_id:
                alt = next((v.voice_id for v in voices if v.voice_id != voice_id), None)
            if not alt:
                raise
            return self._convert(client, alt, text, out_path)
