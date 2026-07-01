"""plan_repair 순수 단위 테스트. conformance fail -> 교정 액션 매핑을 검증한다."""

from reel_gen_agent.generate.conformance import (
    ConformanceCheck,
    ConformanceConfig,
    ConformanceReport,
)
from reel_gen_agent.generate.repair import (
    GENERATED_LUFS_MAX,
    GENERATED_LUFS_MIN,
    LOUDNESS_MARGIN,
    plan_repair,
)

_CONFIG = ConformanceConfig(lufs_min=GENERATED_LUFS_MIN, lufs_max=GENERATED_LUFS_MAX)


def _report(passed: bool, *fail_codes: str) -> ConformanceReport:
    checks = [
        ConformanceCheck(code=code, category="perceptual", intrinsic=True, status="fail")
        for code in fail_codes
    ]
    return ConformanceReport(checks=checks, passed=passed)


def test_loudness_too_quiet_nudges_up_to_bound():
    # 측정치가 하한보다 조용하면 목표를 하한 안쪽(margin)으로 올린다.
    report = _report(False, "perceptual.volume_loudness")
    action = plan_repair(report, _CONFIG, measured_lufs=-24.0, attempts=0)
    assert action is not None
    assert action.target == "assemble"
    assert action.loudness_target == round(GENERATED_LUFS_MIN + LOUDNESS_MARGIN, 2)  # -19.5


def test_loudness_too_loud_nudges_down_to_bound():
    # 측정치가 상한보다 크면 목표를 상한 안쪽(margin)으로 내린다.
    report = _report(False, "perceptual.volume_loudness")
    action = plan_repair(report, _CONFIG, measured_lufs=-3.0, attempts=0)
    assert action is not None
    assert action.loudness_target == round(GENERATED_LUFS_MAX - LOUDNESS_MARGIN, 2)  # -10.5


def test_passed_report_no_action():
    report = _report(True)
    assert plan_repair(report, _CONFIG, measured_lufs=-24.0, attempts=0) is None


def test_attempts_cap_returns_none():
    # 상한(3회) 소진이면 fail이어도 더 되돌리지 않는다.
    report = _report(False, "perceptual.volume_loudness")
    assert plan_repair(report, _CONFIG, measured_lufs=-24.0, attempts=3) is None


def test_non_loudness_fail_not_repairable():
    # loudness 외 결정론 fail은 교정 파라미터가 없어 되돌리지 않는다(no-op 방지).
    report = _report(False, "template.fps_match")
    assert plan_repair(report, _CONFIG, measured_lufs=-15.0, attempts=0) is None


def test_loudness_fail_but_measured_in_range_no_action():
    # loudness fail로 표시됐지만 측정치가 범위 안이면(측정 불일치) 손대지 않는다.
    report = _report(False, "perceptual.volume_loudness")
    assert plan_repair(report, _CONFIG, measured_lufs=-15.0, attempts=0) is None


def test_loudness_fail_but_unmeasured_no_action():
    report = _report(False, "perceptual.volume_loudness")
    assert plan_repair(report, _CONFIG, measured_lufs=None, attempts=0) is None
