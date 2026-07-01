"""Veo 영상 백엔드. 패널 스틸 + 프롬프트로 image-to-video 클립을 만든다(Vertex lane 전용).

[ai-model-records.md] §4: Veo 3.1은 항상 Vertex AI lane으로 호출하고 출력은 GCS로 떨어진다
(`VEO_OUTPUT_GCS_URI`). Veo는 4/6/8초만 만들므로, 짧은 컷은 최소 길이로 생성한 뒤 패널
길이에 맞춰 자른다. voice는 나레이션(voiceover)이 기본이라 `generate_audio=False`로 둔다.
호출/다운로드가 실패하면 RuntimeError를 올려 호출 측이 켄 번스로 폴백하게 한다.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

_ALLOWED_VEO_SEC = (4, 6, 8)
_POLL_SEC = 10
_MAX_WAIT_SEC = 600


def _veo_seconds(duration_sec: float) -> int:
    """패널 길이를 Veo가 만들 수 있는 최소 허용 길이로 올림한다(4/6/8)."""
    for s in _ALLOWED_VEO_SEC:
        if duration_sec <= s:
            return s
    return _ALLOWED_VEO_SEC[-1]


def _download_gcs(uri: str, out_path: str) -> None:
    """gs://bucket/blob -> 로컬 파일."""
    from google.cloud import storage

    assert uri.startswith("gs://"), uri
    bucket_name, _, blob_name = uri[len("gs://") :].partition("/")
    client = storage.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    client.bucket(bucket_name).blob(blob_name).download_to_filename(out_path)


class VeoBackend:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("VEO_MODEL") or "veo-3.1-fast-generate-001"
        self.gcs_uri = os.environ.get("VEO_OUTPUT_GCS_URI")

    def render_panel(
        self,
        still_path: str,
        duration_sec: float,
        width: int,
        height: int,
        fps: int,
        out_path: str,
        motion: str = "",
        prompt: str = "",
    ) -> str:
        from google.genai import types

        from ...analysis.gemini_client import make_client, select_backend

        selection = select_backend()
        if selection is None or selection[0] != "vertex":
            raise RuntimeError("Veo는 Vertex 자격이 필요하다(GOOGLE_CLOUD_PROJECT + ADC).")
        if not self.gcs_uri:
            raise RuntimeError("VEO_OUTPUT_GCS_URI가 필요하다.")
        client = make_client(selection)

        with open(still_path, "rb") as fh:
            image = types.Image(image_bytes=fh.read(), mime_type="image/png")
        config = types.GenerateVideosConfig(
            aspect_ratio="9:16",
            number_of_videos=1,
            duration_seconds=_veo_seconds(duration_sec),
            resolution="1080p" if width >= 1080 else "720p",
            generate_audio=False,  # voiceover는 별도 TTS
            # 인물(성인) 생성을 허용해야 캐릭터 image-to-video가 RAI 필터에 안 막힌다.
            person_generation="allow_adult",
            output_gcs_uri=self.gcs_uri,
        )
        op = client.models.generate_videos(
            model=self.model,
            prompt=prompt or "cinematic vertical beauty short",
            image=image,
            config=config,
        )
        waited = 0
        while not op.done and waited < _MAX_WAIT_SEC:
            time.sleep(_POLL_SEC)
            waited += _POLL_SEC
            op = client.operations.get(op)
        if not op.done or not getattr(op, "response", None):
            raise RuntimeError("Veo 생성 미완료/응답 없음")
        videos = op.response.generated_videos or []
        if not videos:
            raise RuntimeError("Veo 결과 영상 없음")
        uri = videos[0].video.uri
        raw = str(Path(out_path).with_suffix(".veo.mp4"))
        _download_gcs(uri, raw)

        # 패널 길이로 자르고 목표 해상도/프레임레이트로 맞춘다.
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            raw,
            "-t",
            f"{duration_sec:.3f}",
            "-vf",
            vf,
            "-r",
            str(fps),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            out_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path
