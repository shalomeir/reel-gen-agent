"""결정론 조립. 샷 클립 concat + 자막 오버레이 + 오디오 mux -> final.mp4.

같은 Materials는 같은 결과를 낸다(재현성). 컨테이너/코덱은 trd.md 가드레일(mp4/H.264/AAC).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .schema import InputMeta, Materials


def assemble(materials: Materials, meta: InputMeta, out_path: str) -> str:
    if not materials.shot_clips:
        raise ValueError("assemble: shot_clips is empty")
    # 워킹 스켈레톤: concat demuxer로 클립을 잇는다. (자막 오버레이/믹스는 다음 태스크에서)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for clip in materials.shot_clips:
            f.write(f"file '{Path(clip).resolve()}'\n")
        listfile = f.name
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        listfile,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(meta.fps),
        "-c:a",
        "aac",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
