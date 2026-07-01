"""관측 trace: 로컬 JSONL이 진실의 원천, Langfuse는 옵션 sink([ADR.md] ADR-0013).

그래프 노드가 `Tracer.node(name)` 컨텍스트로 span을 열면, 항상 켜진 로컬 JSONL sink가
`logs/<session_id>/runs/<run_id>/trace.jsonl`에 한 줄씩 쓴다. LANGFUSE_* 키가 있으면
Langfuse sink도 붙는다(없으면 조용히 무력화, 실패해도 실행을 막지 않는다).

session_id/run_id는 로그 경로와 Langfuse 식별자에 동일하게 쓴다(대조 가능). 시간은
호출 측이 datetime을 주입한다(스크립트 환경 제약과 무관하게 결정적으로 두기 위함).
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def _logs_root() -> Path:
    return Path(os.environ.get("REEL_LOGS_DIR", "logs"))


class Tracer:
    """노드 span을 로컬 JSONL(+옵션 Langfuse)로 남긴다. 실패는 절대 실행을 막지 않는다."""

    def __init__(self, session_id: str, run_id: str) -> None:
        self.session_id = session_id
        self.run_id = run_id
        self._dir = _logs_root() / session_id / "runs" / run_id
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._trace = self._dir / "trace.jsonl"
        self._seq = 0
        self._lf = _langfuse_client()

    def _write(self, event: dict[str, Any]) -> None:
        event = {"session_id": self.session_id, "run_id": self.run_id, **event}
        try:
            with open(self._trace, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass  # 로깅 실패는 무시(실행 우선)

    def event(self, kind: str, name: str, **data: Any) -> None:
        self._seq += 1
        self._write({"seq": self._seq, "kind": kind, "name": name, **data})

    @contextmanager
    def node(self, name: str, **meta: Any):
        """노드 실행 span. 시작/종료(또는 에러)를 trace에 남긴다."""
        self.event("node_start", name, **meta)
        lf_span = None
        if self._lf is not None:
            try:
                lf_span = self._lf.start_span(name=name, metadata=meta or None)
            except Exception:
                lf_span = None
        try:
            yield self
        except Exception as exc:  # 에러도 남기고 다시 올린다
            self.event("node_error", name, error=str(exc))
            if lf_span is not None:
                try:
                    lf_span.update(level="ERROR", status_message=str(exc))
                    lf_span.end()
                except Exception:
                    pass
            raise
        else:
            self.event("node_end", name)
            if lf_span is not None:
                try:
                    lf_span.end()
                except Exception:
                    pass


def _langfuse_client():
    """LANGFUSE_* 키가 다 있으면 Langfuse 클라이언트, 아니면 None(조용히 무력화)."""
    need = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    if not all(os.environ.get(k) for k in need):
        return None
    try:
        from langfuse import Langfuse

        return Langfuse()
    except Exception:
        return None


def make_session_id(stamp: str, short_hash: str) -> str:
    """session_id = YYYYMMDD-HHMMSS-<짧은해시>. 시간·해시는 호출 측이 주입한다."""
    return f"{stamp}-{short_hash}"
