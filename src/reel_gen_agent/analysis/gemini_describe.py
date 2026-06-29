"""Gemini 멀티모달로 비정형 속성을 묘사한다.

목소리 톤, 영상 느낌/무드, 자막 스타일, 후크, 내러티브를 구조화 출력(JSON)으로 받는다.
기본 경로는 File API로 영상을 통째 업로드(오디오 포함). 영상 스트림이 콘텐츠 필터에
블록되거나 영상이 길면 키프레임 이미지 경로로 자동 폴백한다.
키가 없거나 호출이 끝까지 실패하면 빈 결과 + 경고를 반환해 정형 계층만으로도
분석이 끝나게 한다.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from .profile import GeminiDescription

# 통째 업로드를 쓸 길이 상한(초). 넘으면 키프레임 폴백.
WHOLE_UPLOAD_MAX_SEC = 60.0
DEFAULT_MODEL = "gemini-2.5-flash"
# File API 업로드 후 처리 완료를 기다리는 최대 시간(초).
UPLOAD_POLL_TIMEOUT_SEC = 120
# 키프레임 폴백에서 뽑을 프레임 수.
FALLBACK_FRAMES = 8

_BASE_PROMPT = """\
You are a short-form video analyst for a vertical product-ad generation harness.
Fill the structured schema, focusing on perceptual qualities a numeric pipeline cannot capture:
- voice: is there narration/dialogue? If so, describe the vocal tone and pace. If only BGM, present=false.
- music_dynamics: "build" if the audio energy clearly rises toward a payoff, else "flat".
- music_beat_synced: do the cuts land on musical beats, or follow meaning/action?
- subtitle: transcribe on-screen caption text, and describe font_style, color, position
  (top/center/bottom/mixed), density (keyword vs full_transcript), and any emoji used.
- visual_palette: dominant color mood words (e.g. "warm beige", "soft pink").
- visual_motion: still / gentle / dynamic.
- hook (first 3s): headline, product_line, bottom_caption, and the visual hook.
- tone: mood labels (e.g. fresh, clinical, sensorial, cinematic, ugc, authentic).
- narrative_arc: ordered beats (e.g. ["problem", "apply", "payoff"]).
- description: one vivid Korean paragraph describing the voice tone and overall feel of the video.

Write `description` in Korean. Keep other string fields concise.
"""

# 영상 경로용 / 프레임 폴백용 프롬프트. 폴백은 오디오가 없음을 모델에 알린다.
PROMPT_VIDEO = "Analyze this vertical short video.\n" + _BASE_PROMPT
PROMPT_FRAMES = (
    f"These are {FALLBACK_FRAMES} keyframes (no audio) sampled in order from a "
    "vertical skincare short video.\n"
    + _BASE_PROMPT
    + "\nAudio is unavailable here: set voice.present only if text/lips clearly imply speech, "
    "and leave music fields null."
)


def _get_client(api_key: str):
    """google-genai 클라이언트를 만든다. SDK 미설치 시 명확히 알린다."""
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - 환경 문제
        raise RuntimeError("google-genai 패키지가 필요합니다: pip install google-genai") from exc
    return genai.Client(api_key=api_key)


def _ascii_safe_path(path: str, tmp_dir: str) -> str:
    """비ASCII 파일명은 File API 업로드 시 인코딩 에러를 내므로 안전한 이름으로 복사한다."""
    if Path(path).name.isascii():
        return path
    safe = str(Path(tmp_dir) / f"upload{Path(path).suffix}")
    shutil.copy2(path, safe)
    return safe


def _upload_and_wait(client, path: str):
    """File API로 업로드하고 처리(ACTIVE)가 끝날 때까지 폴링한다."""
    uploaded = client.files.upload(file=path)
    deadline = time.time() + UPLOAD_POLL_TIMEOUT_SEC
    while uploaded.state.name == "PROCESSING":
        if time.time() > deadline:
            raise TimeoutError("Gemini File API 처리 시간 초과")
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state.name == "FAILED":
        raise RuntimeError("Gemini File API 업로드 처리 실패")
    return uploaded


def _frame_parts(path: str, types) -> list:
    """영상에서 균등 간격 키프레임을 JPEG Part 리스트로 만든다."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    parts: list = []
    if total > 0:
        for idx in np.linspace(0, total - 1, num=FALLBACK_FRAMES, dtype=int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok:
                continue
            ok, buf = cv2.imencode(".jpg", frame)
            if ok:
                parts.append(types.Part.from_bytes(data=buf.tobytes(), mime_type="image/jpeg"))
    cap.release()
    return parts


def _generate(client, types, model, contents) -> GeminiDescription | None:
    """구조화 출력으로 한 번 호출한다. 블록/빈 응답이면 None을 반환한다."""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=GeminiDescription,
    )
    response = client.models.generate_content(model=model, contents=contents, config=config)
    parsed = response.parsed
    if isinstance(parsed, GeminiDescription):
        return parsed
    if response.text:
        return GeminiDescription.model_validate_json(response.text)
    return None


def describe(
    path: str,
    duration_sec: float | None,
    api_key: str | None = None,
    model: str | None = None,
) -> GeminiDescription:
    """영상을 Gemini로 분석해 비정형 묘사를 반환한다.

    경로 선택: 짧은 영상은 통째 업로드(오디오 포함) 우선. 블록/빈 응답이면 키프레임
    폴백. 긴 영상은 처음부터 키프레임. 끝까지 실패해도 예외 없이 빈 결과를 낸다.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    model = model or os.environ.get("GEMINI_ANALYSIS_MODEL", DEFAULT_MODEL)

    if not api_key:
        print("[gemini_describe] GEMINI_API_KEY 없음 - 비정형 계층 건너뜀", file=sys.stderr)
        return GeminiDescription()

    try:
        from google.genai import types

        client = _get_client(api_key)
        short = duration_sec is None or duration_sec <= WHOLE_UPLOAD_MAX_SEC

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1순위: 영상 통째 업로드 (짧을 때만)
            if short:
                upload_path = _ascii_safe_path(path, tmp_dir)
                uploaded = _upload_and_wait(client, upload_path)
                result = _generate(client, types, model, [uploaded, PROMPT_VIDEO])
                if result is not None:
                    return result
                print(
                    "[gemini_describe] 영상 경로 블록/빈 응답 - 키프레임 폴백",
                    file=sys.stderr,
                )

            # 2순위: 키프레임 이미지 폴백
            frames = _frame_parts(path, types)
            if frames:
                result = _generate(client, types, model, frames + [PROMPT_FRAMES])
                if result is not None:
                    return result

        print("[gemini_describe] 비정형 분석 빈 결과 - 정형 계층만 사용", file=sys.stderr)
        return GeminiDescription()
    except Exception as exc:  # 분석 전체를 죽이지 않는다.
        print(f"[gemini_describe] 비정형 분석 실패: {exc}", file=sys.stderr)
        return GeminiDescription()
