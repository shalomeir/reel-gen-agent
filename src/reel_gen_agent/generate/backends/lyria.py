"""BGM 생성 백엔드. Lyria(Vertex predict). 실패하면 호출 측이 합성 베드로 폴백한다.

[ai-model-records.md] §5: 1차 Lyria(`LYRIA_MODEL`). genai SDK에는 단순 음악 생성 메서드가
없어 Vertex AI `:predict` REST를 직접 호출한다(google-auth의 인증 세션 재사용). Lyria는
리전 제약이 있어(대개 us-central1) `LYRIA_LOCATION`으로 고정한다. 응답은 base64 오디오다.
컷 주기에 맞춘 bpm을 프롬프트에 실어 컷-음악 동기를 유도한다.
"""

from __future__ import annotations

import base64
import os


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
            # 스타일 어구는 붙이지 않는다(장르는 음악 노드가 prompt로 이미 정함). bpm만 컷
            # 리듬 정렬용으로 덧붙인다. "instrumental"은 나레이션 아래 베드라는 형식 제약.
            "instances": [{"prompt": f"{prompt}, around {bpm} bpm, instrumental"}],
            "parameters": {"sample_count": 1},
        }
        # 설정 모델을 먼저, 실패하면 predict GA 모델(lyria-002)로 재시도한다(모델명·리전 흔들림 방어).
        models: list[str] = []
        for mdl in (self.model, "lyria-002"):
            if mdl and mdl not in models:
                models.append(mdl)

        last_error: Exception | None = None
        for mdl in models:
            url = (
                f"https://{self.location}-aiplatform.googleapis.com/v1/projects/"
                f"{self.project}/locations/{self.location}/publishers/google/models/{mdl}:predict"
            )
            try:
                resp = session.post(
                    url, data=_json.dumps(body),
                    headers={"Content-Type": "application/json"}, timeout=180,
                )
                resp.raise_for_status()
                preds = resp.json().get("predictions") or []
                b64 = (preds[0].get("bytesBase64Encoded") or preds[0].get("audioContent")) if preds else None
                if not b64:
                    raise RuntimeError("Lyria 응답에 오디오 없음")
                with open(out_path, "wb") as f:
                    f.write(base64.b64decode(b64))
                return out_path
            except Exception as exc:  # 다음 모델로 재시도
                last_error = exc
        raise RuntimeError(f"Lyria 생성 실패: {last_error}")
