"""크리에이티브 레인(실행마다 스타일 다양화) 테스트."""

import random

from reel_gen_agent.generate.variety import LANES, CreativeLane, pick_lane


def test_lanes_cover_fast_and_slow_and_bgm_led():
    pacings = {lane.pacing for lane in LANES}
    assert "fast_montage" in pacings and "slow_demo" in pacings and "mixed" in pacings
    prominences = {lane.music_prominence for lane in LANES}
    assert "prominent" in prominences and "background" in prominences
    # BGM 중심(느린 + prominent + sparse) 레인이 최소 하나 있다.
    assert any(
        lane.pacing == "slow_demo"
        and lane.music_prominence == "prominent"
        and lane.narration_density == "sparse"
        for lane in LANES
    )


def test_pick_lane_returns_a_lane():
    assert isinstance(pick_lane(), CreativeLane)


def test_pick_lane_is_deterministic_with_seeded_rng():
    a = pick_lane(random.Random(7))
    b = pick_lane(random.Random(7))
    assert a == b  # 같은 seed -> 같은 레인(테스트·seed 고정 재현성)


def test_pick_lane_varies_across_seeds():
    # 여러 seed로 뽑으면 서로 다른 레인이 나온다(실행마다 다른 스타일 탐색).
    seen = {pick_lane(random.Random(i)).name for i in range(50)}
    assert len(seen) >= 3
