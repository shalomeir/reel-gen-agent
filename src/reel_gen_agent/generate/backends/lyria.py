"""BGM 생성 백엔드. Lyria(Vertex predict). 실패하면 호출 측이 합성 베드로 폴백한다.

[ai-model-records.md] §5: 1차 Lyria(`LYRIA_MODEL`). genai SDK에는 단순 음악 생성 메서드가
없어 Vertex AI `:predict` REST를 직접 호출한다(google-auth의 인증 세션 재사용). Lyria는
리전 제약이 있어(대개 us-central1) `LYRIA_LOCATION`으로 고정한다. 응답은 base64 오디오다.
컷 주기에 맞춘 bpm을 프롬프트에 실어 컷-음악 동기를 유도한다.

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

    def generate(self, prompt: str, bpm: int, duration_sec: float, out_path: str) -> str:
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
                        url, data=_json.dumps(body),
                        headers={"Content-Type": "application/json"}, timeout=180,
                    )
                    resp.raise_for_status()
                    preds = resp.json().get("predictions") or []
                    b64 = (
                        preds[0].get("bytesBase64Encoded") or preds[0].get("audioContent")
                    ) if preds else None
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
