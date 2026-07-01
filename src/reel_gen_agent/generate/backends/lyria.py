"""BGM 생성 백엔드. Lyria(Vertex predict / Gemini API). 실패하면 호출 측이 합성 베드로 폴백한다.

[ai-model-records.md] §5: 1차 Lyria(`LYRIA_MODEL`). 어느 레인을 쓸지는 `select_backend()`가
정한다(`GENAI_BACKEND=auto`면 Vertex 우선, 자격이 없으면 `GEMINI_API_KEY`).
- Vertex AI lane: `:predict` REST를 직접 호출한다(google-auth 인증 세션 재사용). 리전 제약이
  있어(대개 us-central1) `LYRIA_LOCATION`으로 고정한다. GA 모델(`lyria-002`).
- Gemini Developer API lane: genai SDK의 Interactions API(`interactions.create`)로 Lyria 3를
  호출한다(`GEMINI_API_KEY`). preview 계열 모델(`lyria-3-clip-preview`/`lyria-3-pro-preview`).
어느 쪽이든 응답은 base64 오디오이고, 컷 주기에 맞춘 bpm을 프롬프트에 실어 컷-음악 동기를
유도한다. Gemini 레인은 MP3를 낼 수 있어 out_path 확장자로 트랜스코딩해 계약(.wav)을 지킨다.

Lyria 3 한계(반드시 이 기대치로 쓸 것):
- **인스트루멘털 배경 베드에만 기대라.** 명확한 장르 + 템포 + 에너지 컨투어(강약)를 주면
  결과가 안정적이다. 반대로 **포그라운드 보컬 곡·가사·훅은 신뢰도가 낮다**(AI 보컬이
  촌스럽고 어색). 그래서 이 시스템은 보컬을 아예 시도하지 않는다(항상 instrumental).
- **프롬프트 구체성이 품질을 가른다.** 장르/스타일, 악기구성, 템포/리듬 느낌, 강약을
  세밀히 명시할수록 좋다. 막연하면 밋밋한 기본 베드로 흐려진다(cloud.google.com
  "Ultimate prompting guide for Lyria 3" 프레임워크: 장르+무드+악기+템포/리듬+instrumental).
- **길이 고정 안 됨.** 대략 ~30초 트랙을 내므로 duration_sec는 참고일 뿐, 실제 사용 길이는
  조립(assemble) 단계에서 영상 길이에 맞춰 자른다.
- **일시 실패가 잦다.** 파이프라인이 같은 Vertex 프로젝트를 병렬로 두드리면 429/타임아웃이
  난다. 그래서 모델별 재시도+백오프를 두고, 그래도 실패하면 호출 측이 합성 베드로 폴백한다
  (폴백은 사인 드론이라 실제 음악이 아니며, 폴백 시 stderr에 원인을 남긴다).
"""

from __future__ import annotations

import base64
import os

# 병렬 부하로 인한 일시 실패(429/5xx/타임아웃)를 넘기기 위한 모델별 재시도 횟수/백오프.
_MAX_ATTEMPTS_PER_MODEL = 3
_RETRY_BACKOFF_SEC = 2.0


class LyriaMusicClient:
    def __init__(self, model: str | None = None, location: str | None = None) -> None:
        self.model = model or os.environ.get("LYRIA_MODEL") or "lyria-002"
        # Lyria는 global 리전을 안 받는 경우가 많아 us-central1을 기본으로 둔다.
        self.location = location or os.environ.get("LYRIA_LOCATION") or "us-central1"
        self.project = os.environ.get("GOOGLE_CLOUD_PROJECT")

    def _gemini_model(self) -> str:
        """Gemini 레인용 Lyria 모델. Vertex ID(lyria-002)는 Gemini API에서 안 통하므로
        clip preview로 교정한다. `LYRIA_GEMINI_MODEL` > `LYRIA_MODEL`(lyria-3-* 일 때만) 순."""
        m = os.environ.get("LYRIA_GEMINI_MODEL") or self.model
        return m if "lyria-3" in (m or "").lower() else "lyria-3-clip-preview"

    def generate(self, prompt: str, bpm: int, duration_sec: float, out_path: str) -> str:
        from ...analysis.gemini_client import select_backend

        selection = select_backend()
        if selection is None:
            raise RuntimeError("Lyria 자격 없음(GEMINI_API_KEY 또는 Vertex 자격 필요).")
        if selection[0] == "vertex":
            return self._generate_vertex(prompt, bpm, out_path)
        return self._generate_gemini(selection, prompt, bpm, out_path)

    def _generate_gemini(self, selection, prompt: str, bpm: int, out_path: str) -> str:
        """Gemini Developer API(Interactions)로 Lyria 3 음악을 만든다(GEMINI_API_KEY).

        Lyria 3는 MP3(clip) 또는 MP3/WAV(pro)를 base64로 돌려준다. 받은 오디오를 out_path
        확장자로 트랜스코딩해 파이프라인 계약(.wav)을 지킨다(실제 길이 정렬은 assemble 단계).
        """
        import subprocess
        from pathlib import Path

        from ...analysis.gemini_client import make_client

        client = make_client(selection)
        interaction = client.interactions.create(
            model=self._gemini_model(),
            input=f"{prompt}, around {bpm} bpm",
        )
        audio = getattr(interaction, "output_audio", None)
        data = getattr(audio, "data", None) if audio else None
        if not data:
            raise RuntimeError("Lyria(Gemini) 응답에 오디오 없음")
        src = str(Path(out_path).with_suffix(".lyria.src"))
        with open(src, "wb") as f:
            f.write(base64.b64decode(data))
        subprocess.run(["ffmpeg", "-y", "-i", src, out_path], check=True, capture_output=True)
        return out_path

    def _generate_vertex(self, prompt: str, bpm: int, out_path: str) -> str:
        import json as _json

        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        if not self.project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT가 필요하다(Lyria).")
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        session = AuthorizedSession(creds)
        body = {
            # 스타일·악기·보컬 지시는 호출 측(materials._build_bgm)이 Lyria 프롬프트 프레임워크에
            # 맞춰 이미 완성해 넘긴다(instrumental/vocal 여부 포함). 여기선 컷 리듬 정렬용 bpm만 덧붙인다.
            "instances": [{"prompt": f"{prompt}, around {bpm} bpm"}],
            "parameters": {"sample_count": 1},
        }
        # 설정 모델을 먼저, 실패하면 predict GA 모델(lyria-002)로 재시도한다(모델명·리전 흔들림 방어).
        models: list[str] = []
        for mdl in (self.model, "lyria-002"):
            if mdl and mdl not in models:
                models.append(mdl)

        # 전체 파이프라인이 같은 Vertex 프로젝트를 병렬로 두드리면(Veo·이미지·TTS 동시) Lyria가
        # 일시적 429/5xx/타임아웃을 낸다. 여기서 조금 물러섰다 재시도하지 않으면 호출 측이 곧장
        # 사인 드론 베드로 폴백해 "음악이 노이즈로 나오는" 문제가 된다. 모델별로 짧게 재시도한다.
        import time as _time

        last_error: Exception | None = None
        for mdl in models:
            url = (
                f"https://{self.location}-aiplatform.googleapis.com/v1/projects/"
                f"{self.project}/locations/{self.location}/publishers/google/models/{mdl}:predict"
            )
            for attempt in range(_MAX_ATTEMPTS_PER_MODEL):
                try:
                    resp = session.post(
                        url,
                        data=_json.dumps(body),
                        headers={"Content-Type": "application/json"},
                        timeout=180,
                    )
                    resp.raise_for_status()
                    preds = resp.json().get("predictions") or []
                    b64 = (
                        (preds[0].get("bytesBase64Encoded") or preds[0].get("audioContent"))
                        if preds
                        else None
                    )
                    if not b64:
                        raise RuntimeError("Lyria 응답에 오디오 없음")
                    with open(out_path, "wb") as f:
                        f.write(base64.b64decode(b64))
                    return out_path
                except Exception as exc:  # 재시도 -> 소진하면 다음 모델
                    last_error = exc
                    if attempt + 1 < _MAX_ATTEMPTS_PER_MODEL:
                        _time.sleep(_RETRY_BACKOFF_SEC * (attempt + 1))
        raise RuntimeError(f"Lyria 생성 실패: {last_error}")
