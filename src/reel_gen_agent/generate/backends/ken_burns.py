"""켄 번스 폴백 백엔드. 스틸을 천천히 줌/팬해 클립을 만든다(외부 모델 없음).

영상 모델 예산이 없어도 파이프라인이 끝까지 도는 워킹 스켈레톤의 기본 경로다
([ADR.md] ADR-0011).
"""

from __future__ import annotations

import subprocess


class KenBurnsBackend:
    def render_panel(
        self,
        still_path: str,
        duration_sec: float,
        width: int,
        height: int,
        fps: int,
        out_path: str,
    ) -> str:
        total = max(1, int(round(duration_sec * fps)))
        # 스틸을 살짝 줌인하며 width x height로 출력. 무음 오디오 트랙을 붙여 mux 호환.
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"zoompan=z='min(zoom+0.0005,1.1)':d={total}:s={width}x{height}:fps={fps}"
        )
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", still_path,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", vf, "-t", f"{duration_sec}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-shortest", out_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path
