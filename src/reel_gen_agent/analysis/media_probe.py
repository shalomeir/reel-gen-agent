"""ffprobe로 컨테이너 메타데이터를 추출한다."""

from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from math import gcd

from .profile import Container


def _run_ffprobe(path: str) -> dict:
    """ffprobe를 JSON 출력 모드로 돌려 스트림·포맷 정보를 받는다."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _aspect_ratio(width: int, height: int) -> str:
    """가로·세로를 기약분수 비율로 환산한다(예: 1080x1920 -> 9:16)."""
    if not width or not height:
        return ""
    divisor = gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def probe_container(path: str) -> Container:
    """영상 파일에서 해상도·fps·길이·종횡비를 뽑아 Container로 반환한다."""
    data = _run_ffprobe(path)

    video_stream = next(
        (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise ValueError(f"비디오 스트림을 찾지 못했습니다: {path}")

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))

    # r_frame_rate는 "24000/1001" 같은 분수 문자열로 온다.
    fps_raw = video_stream.get("r_frame_rate", "0/1")
    fps = float(Fraction(fps_raw)) if "/" in fps_raw else float(fps_raw)

    duration = data.get("format", {}).get("duration")
    duration_sec = round(float(duration), 3) if duration else None

    return Container(
        aspect_ratio=_aspect_ratio(width, height),
        fps=round(fps, 3),
        duration_sec=duration_sec,
        resolution=f"{width}x{height}",
    )


def has_audio_stream(path: str) -> bool:
    """오디오 스트림이 하나라도 있으면 True. conformance의 오디오 존재 체크에 쓴다."""
    try:
        data = _run_ffprobe(path)
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError):
        return False
    return any(s.get("codec_type") == "audio" for s in data.get("streams", []))


def stream_durations(path: str) -> tuple[float | None, float | None]:
    """(비디오 길이, 오디오 길이)를 초로 반환한다. mux 정렬(av_sync) 체크용.

    스트림에 duration 태그가 없으면 그 자리는 None. 둘 다 못 구하면 (None, None).
    """
    try:
        data = _run_ffprobe(path)
    except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError):
        return (None, None)

    def _dur(codec_type: str) -> float | None:
        stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == codec_type),
            None,
        )
        if stream is None:
            return None
        raw = stream.get("duration")
        return float(raw) if raw else None

    return (_dur("video"), _dur("audio"))
