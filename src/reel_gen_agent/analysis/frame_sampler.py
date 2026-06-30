"""균등 간격 프레임 샘플과 그로부터 뽑는 결정론 지표.

conformance 게이트의 블랙/프리즈/플리커 판정에 쓴다. 분석 계층에 두어 생성 계층이
재사용하게 한다(generate -> analysis 의존만 허용). OpenCV로 프레임을 읽어 평균 명도와
다운스케일 그레이 프레임을 돌려준다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 인접 프레임 차이 계산용 다운스케일 크기. 작게 줄여 노이즈를 줄이고 비용을 낮춘다.
_DIFF_SIZE = (32, 32)


@dataclass
class FrameSample:
    """샘플 한 장. 위치(0~1), 평균 명도(0~255), 다운스케일 그레이 프레임."""

    position: float
    mean_luma: float
    gray_small: np.ndarray


def sample_frames(path: str, n: int) -> list[FrameSample]:
    """영상에서 n장을 균등 간격으로 샘플해 FrameSample 목록으로 반환한다.

    프레임을 못 읽으면 그 자리는 건너뛴다. 디코드가 전부 실패하면 빈 목록을 낸다.
    """
    import cv2

    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    samples: list[FrameSample] = []
    if total > 0:
        for idx in np.linspace(0, total - 1, num=n, dtype=int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            small = cv2.resize(gray, _DIFF_SIZE).astype(np.float32)
            samples.append(
                FrameSample(
                    position=float(idx) / max(1, total - 1),
                    mean_luma=float(gray.mean()),
                    gray_small=small,
                )
            )
    cap.release()
    return samples


def black_frame_ratio(samples: list[FrameSample], luma_max: float) -> float:
    """평균 명도가 luma_max 미만인(near-black) 프레임 비율(0~1)."""
    if not samples:
        return 1.0
    black = sum(1 for s in samples if s.mean_luma < luma_max)
    return black / len(samples)


def mean_adjacent_diff(samples: list[FrameSample]) -> float:
    """인접 샘플 프레임 사이 평균 절대 명도차. 작을수록 정지영상에 가깝다."""
    if len(samples) < 2:
        return 0.0
    diffs = [
        float(np.abs(samples[i].gray_small - samples[i - 1].gray_small).mean())
        for i in range(1, len(samples))
    ]
    return float(np.mean(diffs))


def interior_black_flicker(samples: list[FrameSample], luma_max: float) -> bool:
    """중간 구간에 양옆은 밝은데 혼자 near-black인 프레임이 있으면 True(깨진 컷 의심).

    인트로/아웃트로의 정상적인 검은 화면은 제외하려고 양 끝 샘플은 보지 않는다.
    """
    for i in range(1, len(samples) - 1):
        prev_ok = samples[i - 1].mean_luma >= luma_max
        next_ok = samples[i + 1].mean_luma >= luma_max
        if samples[i].mean_luma < luma_max and prev_ok and next_ok:
            return True
    return False
