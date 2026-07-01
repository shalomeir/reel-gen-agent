"""Tracer: 로컬 JSONL(항상) + Langfuse(옵션, 4.x API) 배선 검증. 외부 호출은 가짜로 막는다."""

from __future__ import annotations

import json

import reel_gen_agent.generate.trace as tr
from reel_gen_agent.generate.trace import Tracer


def _events(logs_dir: str, session: str, run: str) -> list[dict]:
    p = f"{logs_dir}/{session}/runs/{run}/trace.jsonl"
    return [json.loads(line) for line in open(p, encoding="utf-8")]


def test_local_jsonl_records_node_lifecycle_and_data(tmp_path, monkeypatch):
    monkeypatch.setenv("REEL_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(tr, "_langfuse_client", lambda: None)  # Langfuse 없음
    t = Tracer("sess", "run")
    with t.node("visuals", seg=2) as span:
        span.set(output="[segment 0] Shot 1: macro CU")
    t.close()
    ev = _events(str(tmp_path / "logs"), "sess", "run")
    kinds = [e["kind"] for e in ev]
    assert kinds == ["node_start", "node_data", "node_end", "run_end"]
    # 프롬프트/출력이 로컬 로그에 실제로 남는다(예전엔 start/end만이라 얇았다).
    data = next(e for e in ev if e["kind"] == "node_data")
    assert "macro CU" in data["output"]


def test_node_error_is_logged_and_reraised(tmp_path, monkeypatch):
    monkeypatch.setenv("REEL_LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(tr, "_langfuse_client", lambda: None)
    t = Tracer("s", "r")
    try:
        with t.node("boom"):
            raise ValueError("nope")
    except ValueError:
        pass
    kinds = [e["kind"] for e in _events(str(tmp_path / "logs"), "s", "r")]
    assert "node_error" in kinds


def test_langfuse_uses_4x_api_root_child_flush(tmp_path, monkeypatch):
    monkeypatch.setenv("REEL_LOGS_DIR", str(tmp_path / "logs"))
    calls: list[str] = []

    class FakeSpan:
        def start_observation(self, **k):
            calls.append("child")
            return FakeSpan()

        def update(self, **k):
            calls.append("update")

        def end(self, **k):
            calls.append("end")

    class FakeLF:
        def start_observation(self, **k):
            calls.append("root")
            return FakeSpan()

        def flush(self):
            calls.append("flush")

    monkeypatch.setattr(tr, "_langfuse_client", lambda: FakeLF())
    t = Tracer("s", "r")
    with t.node("hook") as span:
        span.set(output="hook")
    t.close()
    # 4.x: start_span이 아니라 start_observation. root -> child -> update -> end, 마지막에 flush.
    assert calls[0] == "root"
    assert "child" in calls and "update" in calls and "end" in calls
    assert calls[-1] == "flush"


def test_langfuse_failure_never_breaks_run(tmp_path, monkeypatch):
    monkeypatch.setenv("REEL_LOGS_DIR", str(tmp_path / "logs"))

    class Boom:
        def start_observation(self, **k):
            raise RuntimeError("langfuse down")

        def flush(self):
            raise RuntimeError("langfuse down")

    monkeypatch.setattr(tr, "_langfuse_client", lambda: Boom())
    t = Tracer("s", "r")  # root 생성 실패해도 죽지 않는다
    with t.node("n") as span:
        span.set(output="x")
    t.close()  # flush 실패해도 죽지 않는다
    # 로컬 로그는 그대로 남는다.
    kinds = [e["kind"] for e in _events(str(tmp_path / "logs"), "s", "r")]
    assert "node_start" in kinds and "run_end" in kinds
