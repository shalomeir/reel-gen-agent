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
        variant: int = 0,
    ) -> str:
        total = max(1, int(round(duration_sec * fps)))
        # 컷마다 모션을 바꿔(줌인/줌아웃/좌우 팬/시작 크롭 차이) 인접 클립의 경계 프레임이
        # 확연히 달라지게 한다. 스틸이 서로 비슷해도(같은 캐릭터·팔레트) 컷 감지기가 각
        # 경계를 잡도록 돕는다. 연속 모션이라 not_frozen(인접 프레임 차이)도 통과한다.
        cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
        motions = [
            (f"1+0.18*on/{total}", cx, cy),  # 0: 중앙 줌인
            (f"1.18-0.18*on/{total}", cx, cy),  # 1: 중앙 줌아웃
            ("1.12", f"(iw-iw/zoom)*on/{total}", cy),  # 2: 좌->우 팬
            ("1.12", f"(iw-iw/zoom)*(1-on/{total})", cy),  # 3: 우->좌 팬
            (f"1+0.18*on/{total}", cx, "0"),  # 4: 상단 기준 줌인
            (f"1.18-0.18*on/{total}", cx, "ih-ih/zoom"),  # 5: 하단 기준 줌아웃
        ]
        zoom, xexpr, yexpr = motions[variant % len(motions)]
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"zoompan=z='{zoom}':x='{xexpr}':y='{yexpr}':"
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
