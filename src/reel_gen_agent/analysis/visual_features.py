"""OpenCV로 색 팔레트·밝기·대비를 정량화한다."""

from __future__ import annotations

import cv2
import numpy as np

# 팔레트 추출에 쓸 k-means 군집 수.
PALETTE_K = 4
# 영상에서 균등 간격으로 샘플링할 프레임 수.
SAMPLE_FRAMES = 12


def _sample_frames(path: str, n: int) -> list[np.ndarray]:
    """영상에서 균등 간격으로 n개 프레임을 BGR로 뽑는다."""
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames: list[np.ndarray] = []
    if total <= 0:
        cap.release()
        return frames

    indices = np.linspace(0, total - 1, num=min(n, total), dtype=int)
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    return frames


def _dominant_colors(frames: list[np.ndarray], k: int) -> list[str]:
    """샘플 프레임 화소를 k-means로 군집화해 지배색 hex 목록을 만든다."""
    # 화소 수를 줄이려고 각 프레임을 작게 리사이즈 후 화소를 모은다.
    pixels = []
    for frame in frames:
        small = cv2.resize(frame, (32, 32), interpolation=cv2.INTER_AREA)
        pixels.append(small.reshape(-1, 3))
    if not pixels:
        return []

    data = np.vstack(pixels).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    # cv2.kmeans는 bestLabels=None을 런타임에서 허용하나 타입 스텁이 못 잡는다.
    _, labels, centers = cv2.kmeans(data, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)  # type: ignore[call-overload]

    # 군집 크기 순으로 정렬해 큰 색부터 반환한다.
    counts = np.bincount(labels.flatten(), minlength=k)
    order = np.argsort(counts)[::-1]
    palette = []
    for i in order:
        b, g, r = centers[i]
        palette.append(f"#{int(r):02X}{int(g):02X}{int(b):02X}")
    return palette


def extract_visual_features(path: str):
    """프레임 색·밝기·대비를 (palette, brightness, contrast)로 반환한다."""
    frames = _sample_frames(path, SAMPLE_FRAMES)
    if not frames:
        return [], None, None

    palette = _dominant_colors(frames, PALETTE_K)

    # 밝기·대비는 그레이스케일 평균/표준편차로 계산한다.
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
    stacked = np.concatenate([g.flatten() for g in grays])
    brightness = round(float(np.mean(stacked)), 1)
    contrast = round(float(np.std(stacked)), 1)

    return palette, brightness, contrast
