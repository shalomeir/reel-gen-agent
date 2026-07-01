"""verify 하드 게이트 + loudness repair 루프의 그래프 배선과 노드 라우팅 테스트.

conformance와 라우드니스 측정은 모킹한다(외부 호출·ffmpeg 없이 결정론 로직만 검증).
"""

from contextlib import nullcontext

from reel_gen_agent.analysis.loudness import Loudness
from reel_gen_agent.generate import execute_graph as eg
from reel_gen_agent.generate.conformance import (
    ConformanceCheck,
    ConformanceReport,
)
from reel_gen_agent.generate.repair import GENERATED_LUFS_MIN, LOUDNESS_MARGIN
from reel_gen_agent.generate.schema import RunManifest


class _FakeTracer:
    def node(self, *args, **kwargs):
        return nullcontext()


def _state(attempts: int = 0) -> dict:
    return {
        "final_video": "final.mp4",
        "use_vlm": False,
        "tracer": _FakeTracer(),
        "manifest": RunManifest(),
        "repair_attempts": attempts,
    }


def _loudness_fail() -> ConformanceReport:
    return ConformanceReport(
        checks=[
            ConformanceCheck(
                code="perceptual.volume_loudness", category="perceptual",
                intrinsic=True, status="fail",
            )
        ],
        passed=False,
    )


def _passed() -> ConformanceReport:
    return ConformanceReport(checks=[], passed=True)


def test_graph_has_verify_conditional_edges():
    # verify는 assemble(되돌림)과 describe(진행) 둘로 갈리는 조건 엣지를 갖는다.
    edges = {(e.source, e.target) for e in eg.build_execute_graph().get_graph().edges}
    assert ("assemble", "verify") in edges
    assert ("verify", "assemble") in edges
    assert ("verify", "describe") in edges


def test_verify_routes_back_to_assemble_on_loudness_fail(monkeypatch):
    # 첫 회 loudness fail(너무 조용) -> assemble로 되돌리고 교정 목표를 싣는다.
    monkeypatch.setattr(eg, "verify_conformance", lambda *a, **k: _loudness_fail())
    monkeypatch.setattr(
        eg, "measure_loudness", lambda p: Loudness(lufs=-24.0, peak_dbfs=-3.0, measured=True)
    )
    out = eg._verify_node(_state(attempts=0))
    assert out["repair_route"] == "assemble"
    assert out["repair_attempts"] == 1
    assert out["loudness_target"] == round(GENERATED_LUFS_MIN + LOUDNESS_MARGIN, 2)


def test_verify_soft_passes_when_attempts_exhausted(monkeypatch):
    # 3회 소진이면 fail이어도 describe로 진행하고 미해결 fail을 기록한다.
    monkeypatch.setattr(eg, "verify_conformance", lambda *a, **k: _loudness_fail())
    monkeypatch.setattr(
        eg, "measure_loudness", lambda p: Loudness(lufs=-24.0, peak_dbfs=-3.0, measured=True)
    )
    out = eg._verify_node(_state(attempts=3))
    assert out["repair_route"] == "describe"
    assert "perceptual.volume_loudness" in out["unresolved"]
    assert "loudness_target" not in out


def test_verify_passes_routes_to_describe(monkeypatch):
    # 통과면 교정 없이 describe로, loudness_target을 남기지 않는다.
    monkeypatch.setattr(eg, "verify_conformance", lambda *a, **k: _passed())
    monkeypatch.setattr(
        eg, "measure_loudness", lambda p: Loudness(lufs=-15.0, peak_dbfs=-3.0, measured=True)
    )
    out = eg._verify_node(_state(attempts=0))
    assert out["repair_route"] == "describe"
    assert out["unresolved"] == []
    assert "loudness_target" not in out
