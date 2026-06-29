"""PySceneDetect로 컷 경계를 찾아 컷 분포를 산출한다."""

from __future__ import annotations

from statistics import mean

from scenedetect import ContentDetector, SceneManager, open_video

from .profile import Cut

# 컷 모드 판정 경계(초). 평균 컷 길이가 이보다 짧으면 빠른 몽타주로 본다.
FAST_MONTAGE_THRESHOLD_SEC = 1.2
# 느린 시연으로 보는 경계. 평균이 이보다 길면 slow_demo.
SLOW_DEMO_THRESHOLD_SEC = 2.0


def _classify_mode(mean_sec: float) -> str:
    """평균 컷 길이로 편집 모드를 라벨링한다."""
    if mean_sec <= FAST_MONTAGE_THRESHOLD_SEC:
        return "fast_montage"
    if mean_sec >= SLOW_DEMO_THRESHOLD_SEC:
        return "slow_demo"
    return "mixed"


def detect_cuts(path: str, threshold: float = 27.0) -> Cut:
    """영상에서 컷 리스트와 분포를 뽑는다.

    threshold는 ContentDetector 기본값(27.0)을 따른다. 값이 낮을수록 더 민감하게
    컷을 잡는다. 숏폼 광고의 빠른 디졸브까지 잡으려면 낮춰서 재실행할 수 있다.
    """
    video = open_video(path)
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))
    scene_manager.detect_scenes(video)

    scene_list = scene_manager.get_scene_list()

    # 각 씬의 시작 타임스탬프(초)와 길이(초)를 구한다.
    starts = [scene[0].get_seconds() for scene in scene_list]
    durations = [scene[1].get_seconds() - scene[0].get_seconds() for scene in scene_list]

    if not durations:
        # 컷이 하나도 안 잡히면(단일 롱테이크) 전체를 1컷으로 본다.
        return Cut(count=1, mode="single_take")

    mean_sec = round(mean(durations), 3)
    # 첫 컷의 시작(0.0)은 의미 없으니 컷 경계 타임스탬프는 두 번째 씬부터.
    boundaries = [round(s, 3) for s in starts[1:]]

    return Cut(
        count=len(durations),
        mean_sec=mean_sec,
        min_sec=round(min(durations), 3),
        max_sec=round(max(durations), 3),
        mode=_classify_mode(mean_sec),
        timestamps=boundaries,
    )
