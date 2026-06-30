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
        # 클립 내내 1.0 -> 1.18로 연속 선형 줌인하며 중앙을 유지한다. 프레임당 일정하게
        # 변해 conformance의 not_frozen(인접 프레임 차이) 임계값을 넘긴다. 조기에 줌 상한에
        # 닿아 정적이 되던 옛 방식(zoom+0.0005, cap 1.1)을 대체한다. 무음 트랙은 mux 호환용.
        zoom = f"1+0.18*on/{total}"
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={total}:s={width}x{height}:fps={fps}"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            still_path,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf",
            vf,
            "-t",
            f"{duration_sec}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-shortest",
            out_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path
