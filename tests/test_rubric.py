"""드라이버 Rubric 수식의 결정론 테스트.

Gemini 저지는 외부 호출이라 목으로 막고, 정규화/게이트/가중합/통과 판정만 실제 단언으로
덮는다. 계약은 specs/rubric.md.
"""

from reel_gen_agent.analysis.profile import VideoProfile
from reel_gen_agent.analysis.rubric import (
    DIMENSIONS,
    RubricGateConfig,
    RubricJudgment,
    compute_result,
    evaluate_video,
    normalize,
)

ALL_CODES = [code for code, *_ in DIMENSIONS]


def _scores(value: int) -> dict[str, int]:
    """7개 차원 전부에 같은 점수."""
    return {code: value for code in ALL_CODES}


def test_dimension_weights_sum_to_one():
    """비중 합은 1.0이어야 한다(보조 flat_score의 전제)."""
    total = sum(weight for _, _, _, weight, _ in DIMENSIONS)
    assert abs(total - 1.0) < 1e-9


def test_normalize_anchors():
    """1점 -> 0.0(실패), 3점 -> 0.5, 5점 -> 1.0(탁월)."""
    assert normalize(1) == 0.0
    assert normalize(3) == 0.5
    assert normalize(5) == 1.0
    # 범위 밖은 클램프된다.
    assert normalize(0) == 0.0
    assert normalize(9) == 1.0


def test_all_fives_is_perfect_hundred():
    """모두 5점이면 게이트 계수 1, 가산 코어 1, gated_score 100."""
    result = compute_result(_scores(5))
    assert result.gate_coefficient == 1.0
    assert result.additive_core == 1.0
    assert result.gated_score == 100.0
    assert result.flat_score == 100.0
    assert result.gate_passed is True
    assert result.passed is True


def test_all_threes_is_compressed():
    """모두 3점이면 곱셈 게이트로 강하게 압축된다(0.5*0.5*0.5*100 = 12.5)."""
    result = compute_result(_scores(3))
    assert result.gate_coefficient == 0.25  # 0.5 * 0.5
    assert result.additive_core == 0.5
    assert result.gated_score == 12.5
    # 보조 flat은 모두 0.5라 50.0
    assert result.flat_score == 50.0


def test_gate_closed_zeroes_total():
    """D1이 1점(실패)이면 가산이 아무리 높아도 gated_score는 0이다."""
    scores = _scores(5)
    scores["D1"] = 1
    result = compute_result(scores)
    assert result.gate_coefficient == 0.0
    assert result.gated_score == 0.0
    assert result.gate_passed is False
    assert result.passed is False
    # 보조 flat은 게이트 압축이 없어 0이 아니다.
    assert result.flat_score > 0


def test_gate_pass_requires_min_gate_score():
    """D1, D2가 기본 임계값 3 미만이면 gate_passed=False."""
    scores = _scores(5)
    scores["D2"] = 2
    result = compute_result(scores)
    assert result.gate_passed is False
    assert result.passed is False


def test_min_total_threshold_blocks_pass():
    """게이트는 열려도 gated_score가 min_total 미만이면 통과 못 한다."""
    # 모두 3점: gated_score 12.5. 기본 min_total 40 미만이라 미달.
    result = compute_result(_scores(3))
    assert result.gate_passed is True
    assert result.passed is False
    # min_total을 낮추면 통과한다.
    loose = compute_result(_scores(3), config=RubricGateConfig(min_total=10.0))
    assert loose.passed is True


def test_weights_drive_additive_core():
    """가산 코어는 가중치 표를 따른다. 비중 큰 D3만 5점이면 작은 D6만 5점보다 높다."""
    base = _scores(1)
    only_d3 = dict(base, D3=5)
    only_d6 = dict(base, D6=5)
    r3 = compute_result(only_d3)
    r6 = compute_result(only_d6)
    assert r3.additive_core > r6.additive_core


def test_missing_dimension_defaults_to_failure():
    """판정에서 빠진 차원은 1점(실패)으로 본다."""
    result = compute_result({"D1": 5, "D2": 5})  # D3..D7 누락
    d3 = next(d for d in result.dimensions if d.code == "D3")
    assert d3.score == 1
    assert d3.normalized == 0.0


def test_evaluate_video_with_mock_judge():
    """저지를 주입해 evaluate_video 오케스트레이션을 네트워크 없이 검증한다."""
    profile = VideoProfile()
    profile.container.duration_sec = 15.0
    profile.source.path = "fake.mp4"

    def fake_judge(path, duration_sec, api_key=None, model=None):
        assert duration_sec == 15.0
        return RubricJudgment(
            dimensions=[
                {"code": code, "score": 4, "rationale": f"{code} 근거"} for code in ALL_CODES
            ],
            summary="총평",
        )

    result = evaluate_video("fake.mp4", profile=profile, judge_fn=fake_judge)
    assert result.scored is True
    assert result.summary == "총평"
    assert len(result.dimensions) == 7
    # 모두 4점: G = 0.75*0.75 = 0.5625, A = 0.75, gated = 42.19
    assert result.gate_coefficient == 0.5625
    assert result.gated_score == 42.19
    assert result.passed is True
    # 근거가 차원에 실린다.
    assert all(d.rationale for d in result.dimensions)


def test_evaluate_video_no_gemini_reports_unscored():
    """--no-gemini면 채점하지 않고 scored=False로 보고한다."""
    profile = VideoProfile()
    profile.source.path = "fake.mp4"
    result = evaluate_video("fake.mp4", profile=profile, use_gemini=False)
    assert result.scored is False
    assert result.passed is False


def test_evaluate_video_handles_judge_failure():
    """저지가 None을 내면(키/호출 실패) scored=False로 게이트를 건너뛰게 한다."""
    profile = VideoProfile()
    profile.source.path = "fake.mp4"
    result = evaluate_video("fake.mp4", profile=profile, judge_fn=lambda *a, **k: None)
    assert result.scored is False
