"""효과음(SFX) 생성 백엔드. ElevenLabs text-to-sound-effects.

프로덕션(비-diegetic) 편집 효과음 전용이다: 컷 전환 whoosh, 그래픽/sparkle 액센트, 시작 후크
라이저, 엔딩 징글/딩 같은 '예능식' 편집 효과. 씬 내 자연음(분사·탭·붓기)은 영상 모델(Veo/
Kling)이 audio 생성으로 내는 게 낫다(사용자 지시). 그래서 SFX는 옵션이며, 스토리보드가 낸
프로덕션 효과 `sfx` 큐가 있고 플랜이 켰을 때만 쓴다. 키(`ELEVENLABS_API_KEY`)가 있을 때만
동작하고, 실패하면 호출 측이 SFX 없이 진행하도록 예외를 올린다.
"""

from __future__ import annotations

import os

# SFX 한 컷 최대 길이(초). 너무 길면 컷을 덮으니 짧게 캡한다.
_MAX_SFX_SEC = 8.0


class ElevenLabsSfxClient:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("ELEVENLABS_SFX_MODEL")
        self.output_format = os.environ.get("ELEVENLABS_OUTPUT_FORMAT") or "mp3_44100_128"

    def generate(self, prompt: str, duration_sec: float, out_path: str) -> str:
        """짧은 SFX를 만든다. duration_sec는 컷 길이에 맞춘다(0.5~8초로 캡)."""
        from elevenlabs.client import ElevenLabs

        client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
        dur = max(0.5, min(_MAX_SFX_SEC, duration_sec))
        kwargs = dict(
            text=prompt,
            duration_seconds=dur,
            output_format=self.output_format,
            prompt_influence=0.5,
        )
        if self.model:
            kwargs["model_id"] = self.model
        audio = client.text_to_sound_effects.convert(**kwargs)
        with open(out_path, "wb") as f:
            for chunk in audio:
                if chunk:
                    f.write(chunk)
        return out_path
