"""실행마다 스타일을 다르게 탐색하기 위한 크리에이티브 레인.

같은 입력이라도 매 실행 서로 다른 '레인'(페이싱 + 음악 비중 + 나레이션 밀도)을 무작위로
골라 결과가 다양해지게 한다(사용자 요구: 때론 bgm 중심 + 느린 컷, 때론 빠르게 등). 확정된
레인 값은 ReelProfile에 남으므로 execute는 그대로 재현한다(같은 profile -> 유사 영상).

원칙:
- **입력·레퍼런스가 명시한 값은 절대 덮지 않는다.** 레인은 아무것도 안 정해진 축에만 적용한다
  (레퍼런스가 style을 시딩하면 그 run엔 레인을 적용하지 않는다).
- 레인은 '기본 편향'을 다양화할 뿐, 제품/캐릭터 같은 내용은 건드리지 않는다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class CreativeLane:
    """한 실행의 연출 방향. 페이싱·음악 비중·나레이션 밀도를 한 조합으로 묶는다."""

    name: str
    pacing: str  # fast_montage / slow_demo / mixed (컷 빈도 -> 컷 수·음악 템포로 파급)
    music_prominence: str  # prominent(BGM 중심) / background(발화·씬 중심)
    narration_density: str  # sparse(대사 최소, BGM이 끌고 감) / normal


# 서로 뚜렷이 다른 인상을 주는 레인들. 조합이 어긋나지 않게 축을 함께 묶는다(독립 랜덤이 아니라
# 코히런트 프리셋). 새 결을 원하면 행을 추가한다(코드가 스타일을 박지 않고 데이터로 둔다).
LANES: tuple[CreativeLane, ...] = (
    CreativeLane("bgm_led_slow", "slow_demo", "prominent", "sparse"),
    CreativeLane("fast_hype", "fast_montage", "prominent", "normal"),
    CreativeLane("balanced_ugc", "mixed", "background", "normal"),
    CreativeLane("calm_voice_led", "slow_demo", "background", "normal"),
    CreativeLane("fast_voice_led", "fast_montage", "background", "normal"),
)


def pick_lane(rng: random.Random | None = None) -> CreativeLane:
    """실행용 크리에이티브 레인을 하나 고른다. rng를 주면 결정적(테스트·seed 고정용)."""
    return (rng or random).choice(LANES)
