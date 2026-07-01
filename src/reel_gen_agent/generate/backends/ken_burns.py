"""켄 번스 폴백 백엔드. 스틸을 천천히 줌하거나 정지로 클립을 만든다(외부 모델 없음).

영상 모델 예산이 없어도 파이프라인이 끝까지 도는 워킹 스켈레톤의 기본 경로다
([ADR.md] ADR-0011). 모션은 beat 기준으로 plan이 골라 넘긴다
([2026-07-01-ken-burns-motion-design.md]).

지터(덜그덕/흔들림) 방지: zoompan은 줌 중심 x/y를 매 프레임 정수 픽셀로 반올림한다. 줌이
서서히 커지면 소수부가 정수 경계를 넘을 때마다 중심이 1px씩 튀어 흔들려 보인다. 원본이
4K여도 출력(1080) 기준으로는 그 튐이 남는다. 그래서 crop 후 출력의 SUPERSAMPLE배로 키운
캔버스 위에서 zoompan을 돌리고 s=WxH로 내린다. 그러면 1px 튐이 출력 기준 1/SUPERSAMPLE
px가 되어 눈에 안 보인다. 좌우 팬은 쓰지 않고 중앙 기준 줌만 한다.

일반 컷은 약한 줌인/줌아웃을 번갈아(plan이 지정) 인접 클립의 경계 프레임을 다르게 해,
스틸이 비슷해도 컷 감지기가 경계를 잡도록 돕는다. 어색해지기 쉬운 좌우 팬은 쓰지 않는다.
"""

from __future__ import annotations

import subprocess

# 모션명 -> zoompan z 식(줌 배율). {total}은 클립 프레임 수로 치환. 전부 중앙 기준(x/y 센터)
# 이라 팬처럼 흔들리지 않는다. `static`은 zoompan을 쓰지 않는 별도 경로라 여기 없다.
_ZOOM_EXPR: dict[str, str] = {
    "zoom_in_slow": "1+0.06*on/{total}",  # 평상시: 아주 약한 줌인
    "zoom_out_slow": "1.06-0.06*on/{total}",  # 평상시 교대: 아주 약한 줌아웃
    "push_in": "1+0.12*on/{total}",  # hook: 조금 더 또렷하게 밀고 들어감
    "product_push_in": "1+0.18*on/{total}",  # 제품 강조 컷: 제품으로 또렷하게 줌인
}
DEFAULT_MOTION = "zoom_in_slow"

# zoompan의 정수 픽셀 반올림 지터를 없애기 위한 오버샘플 배율. 출력의 이 배로 키운 캔버스
# 위에서 줌해서 1px 튐이 출력 기준 1/SUPERSAMPLE px가 되게 한다(4면 눈에 안 보인다).
SUPERSAMPLE = 4


class KenBurnsBackend:
    def render_panel(
        self,
        still_path: str,
        duration_sec: float,
        width: int,
        height: int,
        fps: int,
        out_path: str,
        motion: str = DEFAULT_MOTION,
        prompt: str = "",
        generate_audio: bool = False,  # 인터페이스 통일용(켄 번스는 항상 무음 트랙)
    ) -> str:
        total = max(1, int(round(duration_sec * fps)))
        # 원본 해상도에서 목표 종횡비로만 잘라낸다(crop은 x/y 생략 시 중앙). 최종 축소는
        # zoompan(줌) 또는 scale(정지)이 맡아 부드럽게 내린다.
        crop = f"crop='min(iw,ih*{width}/{height})':'min(ih,iw*{height}/{width})'"

        if motion == "static":
            # zoompan 없이 스틸을 그대로 반복 = 완전 정지(지터 원천 차단).
            vf = f"{crop},scale={width}:{height}"
        else:
            zexpr = _ZOOM_EXPR.get(motion, _ZOOM_EXPR[DEFAULT_MOTION]).format(total=total)
            # crop 후 출력의 SUPERSAMPLE배 캔버스로 키우고, 그 위에서 zoompan을 돌려 s=WxH로
            # 내린다. zoompan의 x/y 정수 반올림(1px 튐)이 출력 기준 서브픽셀이 되어 매끄럽다.
            work_w, work_h = width * SUPERSAMPLE, height * SUPERSAMPLE
            vf = (
                f"{crop},scale={work_w}:{work_h}:flags=bicubic,"
                f"zoompan=z='{zexpr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
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
            "anullsrc=channel_layout=stereo:sample_rate=44100",  # mux 호환용 무음
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
