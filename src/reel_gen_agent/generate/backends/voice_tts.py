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

# 성별별 프리메이드 보이스 이름 우선순위. 캐릭터 페르소나(voice_desc)의 성별에 맞춰 고른다.
# ID가 계정/버전마다 달라(같은 ID가 Sarah로 바뀌기도) 이름으로 계정에서 찾는다.
_FEMALE_VOICE_NAMES = ("bella", "sarah", "alice", "laura", "matilda", "jessica", "lily", "rachel")
_MALE_VOICE_NAMES = ("adam", "antoni", "josh", "arnold", "sam", "charlie", "george", "liam")
_PREFERRED_VOICE_NAMES = _FEMALE_VOICE_NAMES  # 기본(성별 단서 없을 때) 여성 우선


def _persona_gender(voice_desc: str) -> str:
    """voice 페르소나 문자열에서 성별을 읽는다. 남성 단서가 뚜렷하면 male, 아니면 female."""
    d = (voice_desc or "").lower()
    if any(w in d for w in ("male", " man", "guy", "boy", "masculine", "he ", "his ")) and (
        "female" not in d and "woman" not in d
    ):
        return "male"
    return "female"


# 발화 결(desc) -> eleven_v3 오디오 태그. v3는 텍스트 앞 [whispering] 같은 태그로 연기를 바꾼다.
# 레퍼런스 관측 톤/페이스를 태그로 옮겨 '결'을 맞춘다(코드가 스타일을 박지 않고 관측을 반영).
_TONE_TAGS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("whisper",), "[whispering]"),
    (("soft", "gentle", "tender", "delicate"), "[softly]"),
    (("calm", "soothing", "serene", "relaxed"), "[calmly]"),
    (("warm", "appreciative", "intimate"), "[warmly]"),
    (("excited", "enthusiastic", "energetic", "upbeat", "hyped"), "[excited]"),
    (("cheerful", "happy", "playful"), "[cheerfully]"),
    (("confident", "bold", "assertive"), "[confidently]"),
)


def _delivery_tags(voice_desc: str) -> str:
    """voice_desc에서 eleven_v3 연기 태그를 뽑는다(느린 페이스면 [slowly] 추가). 없으면 빈 문자열."""
    d = (voice_desc or "").lower()
    tags: list[str] = []
    for keys, tag in _TONE_TAGS:
        if any(k in d for k in keys) and tag not in tags:
            tags.append(tag)
    if "slow" in d and "[slowly]" not in tags:
        tags.append("[slowly]")
    # 상충 방지: 흥분 계열과 나직 계열이 함께 잡히면 앞선(관측 우선) 것만 남긴다.
    return " ".join(tags[:2])
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

    def _pick_account_voice(self, voices: list, voice_desc: str = "") -> str | None:
        """계정 보이스에서 캐릭터 페르소나에 맞는 보이스를 고른다.

        1) voice_desc의 성별에 맞는 보이스(라벨 gender 또는 선호 이름)를 우선한다.
        2) 성별 일치가 없으면 선호 이름, 그래도 없으면 첫 보이스.
        캐릭터에 맞는 보이스를 골라야 개성이 산다(사용자 지시).
        """
        gender = _persona_gender(voice_desc)
        names = _MALE_VOICE_NAMES if gender == "male" else _FEMALE_VOICE_NAMES

        def _label_gender(v) -> str:
            labels = getattr(v, "labels", None) or {}
            return str(labels.get("gender", "")).lower() if isinstance(labels, dict) else ""

        # 1) 선호 이름(성별별) 우선
        for name in names:
            for v in voices:
                if name in (v.name or "").lower():
                    return v.voice_id
        # 2) 라벨 성별 일치
        for v in voices:
            if _label_gender(v) == gender:
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
        # eleven_v3면 발화 결(voice_desc)을 오디오 태그로 텍스트 앞에 붙여 연기를 맞춘다.
        # 다른 모델은 태그를 그대로 읽어버리므로 붙이지 않는다.
        if "v3" in (self.model or "").lower():
            tags = _delivery_tags(voice_desc)
            if tags:
                text = f"{tags} {text}"
        voices: list | None = None
        voice_id = self.voice_id
        if not voice_id:
            # 명시 지정이 없으면 계정에서 캐릭터 페르소나(성별 등)에 맞는 보이스를 고른다.
            voices = self._account_voices(client)
            voice_id = self._pick_account_voice(voices, voice_desc) or _FALLBACK_VOICE_ID
        try:
            return self._convert(client, voice_id, text, out_path)
        except Exception:
            # 지정 보이스가 막히면(무료 플랜 라이브러리 보이스 등) 다른 계정 보이스로 재시도.
            if voices is None:
                voices = self._account_voices(client)
            alt = self._pick_account_voice(voices, voice_desc)
            if not alt or alt == voice_id:
                alt = next((v.voice_id for v in voices if v.voice_id != voice_id), None)
            if not alt:
                raise
            return self._convert(client, alt, text, out_path)
