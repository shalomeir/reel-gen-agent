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

# 통째 입력을 쓸 길이 상한(초). 넘으면 키프레임 폴백.
WHOLE_UPLOAD_MAX_SEC = 60.0
# File API 업로드 후 처리 완료를 기다리는 최대 시간(초).
UPLOAD_POLL_TIMEOUT_SEC = 120
# Vertex 인라인 바이트 입력의 크기 상한(바이트). Vertex 요청 본문은 ~20MB 제한이라
# 프롬프트 여유를 두고 보수적으로 잡는다. 넘으면 키프레임으로 폴백한다.
VERTEX_INLINE_MAX_BYTES = 18 * 1024 * 1024
# 키프레임 폴백에서 뽑을 프레임 수.
FALLBACK_FRAMES = 8
DEFAULT_MODEL = "gemini-2.5-flash"

T = TypeVar("T", bound=BaseModel)


def resolve_model(model: str | None) -> str:
    """사용할 모델 ID를 정한다. 인자 > 환경변수 > 기본값."""
    return model or os.environ.get("GEMINI_ANALYSIS_MODEL", DEFAULT_MODEL)


def select_backend(api_key_override: str | None = None) -> tuple[str, dict] | None:
    """genai 멀티모달 호출에 쓸 백엔드를 환경에서 고른다.

    `GENAI_BACKEND`로 강제할 수 있다(`vertex`|`gemini`). 기본값 `auto`는 Vertex 자격
    (`GOOGLE_CLOUD_PROJECT` + 서비스계정/액세스 토큰)이 갖춰졌으면 Vertex를 우선해
    Google Cloud 크레딧을 쓰고, 자격이 없으면 `GEMINI_API_KEY`로 내려간다. 어느 쪽도
    자격이 없으면 None을 돌려 호출 측이 결정론 결과만으로 진행하게 한다.

    반환: `("vertex", {"project", "location"})`, `("gemini", {"api_key"})`, 또는 None.
    """
    mode = (os.environ.get("GENAI_BACKEND") or "auto").strip().lower()
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    # 서비스계정 JSON 경로가 정본, 액세스 토큰은 짧은 수동 테스트용 대안이다.
    has_adc = bool(
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        or os.environ.get("GOOGLE_CLOUD_ACCESS_TOKEN")
    )
    vertex_ready = bool(project and has_adc)
    api_key = (
        api_key_override
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    )

    def vertex() -> tuple[str, dict]:
        location = os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
        return "vertex", {"project": project, "location": location}

    def gemini() -> tuple[str, dict] | None:
        return ("gemini", {"api_key": api_key}) if api_key else None

    if mode == "gemini":
        return gemini()
    if mode == "vertex":
        # vertex로 못박았어도 자격이 없으면 Gemini 키로 폴백한다.
        return vertex() if vertex_ready else gemini()
    # auto: Vertex 우선, 자격이 없으면 Gemini.
    return vertex() if vertex_ready else gemini()


def make_client(selection: tuple[str, dict]):
    """선택된 백엔드로 google-genai 클라이언트를 만든다. SDK 미설치 시 명확히 알린다."""
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - 환경 문제
        raise RuntimeError("google-genai 패키지가 필요합니다: pip install google-genai") from exc
    backend, params = selection
    if backend == "vertex":
        # GOOGLE_APPLICATION_CREDENTIALS는 ADC가 자동으로 집는다(키 인자 불필요).
        return genai.Client(
            vertexai=True, project=params["project"], location=params["location"]
        )
    return genai.Client(api_key=params["api_key"])


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


_VIDEO_MIME_BY_SUFFIX = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".m4v": "video/mp4",
}


def whole_video_part(client, types, backend: str, path: str, tmp_dir: str):
    """영상 전체(오디오+모션 포함)를 모델에 넣을 Part를 만든다.

    백엔드마다 영상 입력 방식이 다르다. Gemini 개발자 API는 File API로 업로드하고,
    Vertex는 그 메서드를 지원하지 않으므로 인라인 바이트로 넣는다. 두 경로 모두 영상의
    오디오와 전체 타임라인을 보존한다. Vertex 인라인은 요청 크기 제한이 있어, 상한을
    넘으면 RuntimeError를 던져 호출 측이 키프레임으로 폴백하게 한다.
    """
    if backend == "gemini":
        # File API는 비ASCII 파일명에서 인코딩 에러가 나므로 안전한 이름으로 복사 후 업로드.
        return upload_and_wait(client, ascii_safe_path(path, tmp_dir))

    # Vertex: 인라인 바이트. 큰 영상은 요청 본문 제한을 넘으니 키프레임으로 떨어뜨린다.
    size = os.path.getsize(path)
    if size > VERTEX_INLINE_MAX_BYTES:
        raise RuntimeError(
            f"Vertex 인라인 한도 초과({size}B > {VERTEX_INLINE_MAX_BYTES}B)"
        )
    mime = _VIDEO_MIME_BY_SUFFIX.get(Path(path).suffix.lower(), "video/mp4")
    with open(path, "rb") as fh:
        data = fh.read()
    return types.Part.from_bytes(data=data, mime_type=mime)


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
    model = resolve_model(model)

    selection = select_backend(api_key)
    if selection is None:
        print(
            f"[{log_prefix}] genai 자격 없음(Vertex/GEMINI) - 멀티모달 단계 건너뜀",
            file=sys.stderr,
        )
        return None

    try:
        from google.genai import types

        backend = selection[0]
        client = make_client(selection)
        print(f"[{log_prefix}] 멀티모달 백엔드: {backend}", file=sys.stderr)
        short = duration_sec is None or duration_sec <= WHOLE_UPLOAD_MAX_SEC

        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1순위: 영상 통째 입력 (짧을 때만). 오디오와 전체 모션을 보존한다. 입력 방식만
            # 백엔드별로 다르다(Gemini=File API 업로드, Vertex=인라인 바이트). 입력이 실패해도
            # 키프레임 폴백으로 흘러가야 하므로 바깥 except가 아니라 여기서 잡는다.
            if short:
                try:
                    video_part = whole_video_part(client, types, backend, path, tmp_dir)
                    result = generate_structured(
                        client, types, model, [video_part, video_prompt], schema
                    )
                    if result is not None:
                        return result
                    print(f"[{log_prefix}] 영상 경로 블록/빈 응답 - 키프레임 폴백", file=sys.stderr)
                except Exception as exc:
                    print(
                        f"[{log_prefix}] 영상 통째 입력 실패({exc}) - 키프레임 폴백",
                        file=sys.stderr,
                    )

            # 2순위: 키프레임 이미지 폴백 (Vertex 포함 모든 백엔드 지원)
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
