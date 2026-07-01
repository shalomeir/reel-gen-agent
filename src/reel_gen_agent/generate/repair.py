"""verify(conformance) fail을 교정 액션으로 바꾸는 순수 모듈.

execute 그래프의 verify 노드가 이 모듈로 "무엇을 어떻게 다시 만들지"를 정한다. assemble은
ffmpeg 결정론이라 같은 입력으로 다시 돌리면 같은 fail이 반복된다. 그래서 단순 재실행이 아니라
실패에서 뽑은 교정 파라미터를 다음 재생성에 주입한다. 이번 범위는 loudness 교정 하나다(설계:
docs/superpowers/specs/2026-07-01-verify-repair-loop-design.md).
"""

from __future__ import annotations

from pydantic import BaseModel

from .conformance import ConformanceConfig, ConformanceReport

# loudness 교정 시 위반 경계에서 안쪽으로 밀어 넣는 여유폭(LUFS). 경계에 딱 맞추면 측정 오차로
# 다시 벗어나기 쉬워 margin만큼 안으로 둔다.
LOUDNESS_MARGIN = 1.5
MAX_REPAIR_ATTEMPTS = 3

# execute 그래프의 verify가 생성물에 적용하는 loudness 밴드. 기본 conformance 범위(-30~-5)는
# 레퍼런스 기준선이라 너무 넓어(assemble이 -16/-20으로 맞추면 항상 통과) repair가 죽은 코드가
# 된다. 생성물에는 조금 더 타이트한 밴드를 걸어 극단만이 아니라 결이 어긋난 레벨도 잡는다.
GENERATED_LUFS_MIN = -21.0
GENERATED_LUFS_MAX = -9.0


class RepairAction(BaseModel):
    """conformance fail을 고치기 위한 재생성 지시."""

    target: str  # 되돌릴 노드 이름 (이번 범위에선 "assemble")
    loudness_target: float  # assemble에 주입할 loudnorm 목표(LUFS)


def _loudness_failed(report: ConformanceReport) -> bool:
    return any(c.code == "perceptual.volume_loudness" and c.status == "fail" for c in report.checks)


def unresolved_fails(report: ConformanceReport) -> list[str]:
    """진행 시점에 남은 fail 체크 코드 목록(증거 기록용)."""
    return [c.code for c in report.checks if c.status == "fail"]


def plan_repair(
    report: ConformanceReport,
    config: ConformanceConfig,
    measured_lufs: float | None,
    attempts: int,
    max_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> RepairAction | None:
    """conformance 결과에서 교정 액션을 뽑는다. 교정 불가/상한 소진이면 None(그냥 진행).

    이번 범위: loudness fail만 교정한다. 측정 라우드니스가 허용 범위를 벗어났으면 loudnorm
    목표를 위반한 경계 안쪽(margin)으로 밀어 assemble을 다시 돌리게 한다. 중앙값이 아니라
    경계로 미는 이유는 음악 베드의 '조용한' 의도를 뭉개지 않기 위함이다.
    """
    if report.passed or attempts >= max_attempts:
        return None
    if _loudness_failed(report) and measured_lufs is not None:
        if measured_lufs < config.lufs_min:
            target = config.lufs_min + LOUDNESS_MARGIN
        elif measured_lufs > config.lufs_max:
            target = config.lufs_max - LOUDNESS_MARGIN
        else:
            return None  # loudness fail로 표시됐지만 범위 안(측정 불일치) -> 손대지 않음
        return RepairAction(target="assemble", loudness_target=round(target, 2))
    return None
