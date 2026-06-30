"""Gemini 멀티모달 호출 공용 플러밍.

영상 묘사(gemini_describe)와 Rubric 채점(rubric)이 같은 업로드/폴백 패턴을 쓴다.
그 패턴을 한 곳에 모아 중복을 없앤다. 핵심 진입점은 `run_multimodal`이다.

경로 선택: 짧은 영상은 File API로 통째 업로드(오디오 포함) 우선. 콘텐츠 필터에 블록되거나
빈 응답이면 키프레임 이미지로 폴백. 긴 영상은 처음부터 키프레임. 키가 없거나 끝까지
실패하면 None을 반환해 호출 측이 결정론 결과만으로 진행하게 한다.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

# 통째 업로드를 쓸 길이 상한(초). 넘으면 키프레임 폴백.
WHOLE_UPLOAD_MAX_SEC = 60.0
# File API 업로드 후 처리 완료를 기다리는 최대 시간(초).
UPLOAD_POLL_TIMEOUT_SEC = 120
# 키프레임 폴백에서 뽑을 프레임 수.
FALLBACK_FRAMES = 8
DEFAULT_MODEL = "gemini-2.5-flash"

T = TypeVar("T", bound=BaseModel)


def resolve_model(model: str | None) -> str:
    """사용할 모델 ID를 정한다. 인자 > 환경변수 > 기본값."""
    return model or os.environ.get("GEMINI_ANALYSIS_MODEL", DEFAULT_MODEL)


def make_client(api_key: str):
    """google-genai 클라이언트를 만든다. SDK 미설치 시 명확히 알린다."""
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - 환경 문제
        raise RuntimeError("google-genai 패키지가 필요합니다: pip install google-genai") from exc
    return genai.Client(api_key=api_key)


def ascii_safe_path(path: str, tmp_dir: str) -> str:
    """비ASCII 파일명은 File API 업로드 시 인코딩 에러를 내므로 안전한 이름으로 복사한다."""
    if Path(path).name.isascii():
        return path
    safe = str(Path(tmp_dir) / f"upload{Path(path).suffix}")
    shutil.copy2(path, safe)
    return safe


def upload_and_wait(client, path: str):
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


def frame_parts(path: str, types) -> list:
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


def generate_structured(client, types, model: str, contents, schema: type[T]) -> T | None:
    """구조화 출력으로 한 번 호출한다. 블록/빈 응답이면 None을 반환한다."""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
    )
    response = client.models.generate_content(model=model, contents=contents, config=config)
    parsed = response.parsed
    if isinstance(parsed, schema):
        return parsed
    if response.text:
        return schema.model_validate_json(response.text)
    return None


def run_multimodal(
    path: str,
    duration_sec: float | None,
    schema: type[T],
    video_prompt: str,
    frames_prompt: str,
    api_key: str | None = None,
    model: str | None = None,
    log_prefix: str = "gemini",
) -> T | None:
    """영상을 Gemini에 넣어 구조화 출력을 받는다.

    schema에 맞는 인스턴스를 반환한다. 키가 없거나 끝까지 실패하면 None을 반환한다(예외를
    던지지 않는다). 호출 측은 None을 받으면 결정론 결과만으로 진행한다.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    model = resolve_model(model)

    if not api_key:
        print(f"[{log_prefix}] GEMINI_API_KEY 없음 - 멀티모달 단계 건너뜀", file=sys.stderr)
        return None

    try:
        from google.genai import types

        client = make_client(api_key)
        short = duration_sec is None or duration_sec <= WHOLE_UPLOAD_MAX_SEC

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1순위: 영상 통째 업로드 (짧을 때만)
            if short:
                upload_path = ascii_safe_path(path, tmp_dir)
                uploaded = upload_and_wait(client, upload_path)
                result = generate_structured(client, types, model, [uploaded, video_prompt], schema)
                if result is not None:
                    return result
                print(f"[{log_prefix}] 영상 경로 블록/빈 응답 - 키프레임 폴백", file=sys.stderr)

            # 2순위: 키프레임 이미지 폴백
            frames = frame_parts(path, types)
            if frames:
                result = generate_structured(client, types, model, frames + [frames_prompt], schema)
                if result is not None:
                    return result

        print(f"[{log_prefix}] 멀티모달 빈 결과", file=sys.stderr)
        return None
    except Exception as exc:  # 호출 전체를 죽이지 않는다.
        print(f"[{log_prefix}] 멀티모달 실패: {exc}", file=sys.stderr)
        return None
