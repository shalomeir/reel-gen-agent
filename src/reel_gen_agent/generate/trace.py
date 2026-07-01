"""관측 trace: 로컬 JSONL이 진실의 원천, Langfuse는 옵션 sink([ADR.md] ADR-0013).

그래프 노드가 `Tracer.node(name)` 컨텍스트로 span을 열면, 항상 켜진 로컬 JSONL sink가
`logs/<session_id>/runs/<run_id>/trace.jsonl`에 한 줄씩 쓴다. LANGFUSE_* 키가 있으면
run 단위 root span 아래에 노드 span을 묶어 Langfuse에도 남긴다(없으면 조용히 무력화,
실패해도 실행을 막지 않는다). 실행이 끝나면 `close()`가 root span을 닫고 flush한다 — 짧게
끝나는 CLI에선 flush 없이는 배치 이벤트가 전송되지 않는다.

노드는 `with tracer.node(name) as span:` 으로 받은 handle의 `span.set(input=..., output=...,
prompt=...)`으로 프롬프트·입출력을 남길 수 있다(로컬 JSONL + Langfuse 양쪽). 안 써도 무방하다.

session_id/run_id는 로그 경로와 Langfuse 식별자에 동일하게 쓴다(대조 가능).
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Langfuse span 업데이트에 그대로 넘길 표준 키. 그 외 키는 metadata로 묶는다.
_LF_FIELDS = {"input", "output", "prompt", "level", "status_message", "model", "metadata"}


def _logs_root() -> Path:
    return Path(os.environ.get("REEL_LOGS_DIR", "logs"))


class _NodeHandle:
    """노드 span 핸들. set(...)으로 프롬프트·입출력을 로컬 로그와 Langfuse span에 함께 남긴다."""

    def __init__(self, tracer: Tracer, name: str, lf_span: Any) -> None:
        self._tracer = tracer
        self._name = name
        self._lf_span = lf_span

    def set(self, **data: Any) -> None:
        # 로컬 JSONL: 유의미 데이터(프롬프트·입출력 등)를 이벤트로 남긴다.
        self._tracer.event("node_data", self._name, **data)
        if self._lf_span is None:
            return
        kw = {k: v for k, v in data.items() if k in _LF_FIELDS}
        extra = {k: v for k, v in data.items() if k not in _LF_FIELDS}
        if extra:
            kw["metadata"] = {**(kw.get("metadata") or {}), **extra}
        try:
            self._lf_span.update(**kw)
        except Exception:
            pass


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
        # run 단위 root span. 모든 노드 span을 이 아래에 묶어 Langfuse UI에서 한 trace로 본다.
        self._root = None
        if self._lf is not None:
            try:
                self._root = self._lf.start_observation(
                    name=f"run:{run_id}",
                    as_type="span",
                    metadata={"session_id": session_id, "run_id": run_id},
                )
            except Exception:
                self._root = None

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
        """노드 실행 span. 시작/종료(또는 에러)를 로컬 trace와 Langfuse에 남긴다.

        `as span`으로 받은 handle의 set(...)으로 프롬프트·입출력을 추가로 남길 수 있다.
        """
        self.event("node_start", name, **meta)
        lf_span = None
        if self._root is not None:
            try:
                lf_span = self._root.start_observation(
                    name=name, as_type="span", metadata=meta or None
                )
            except Exception:
                lf_span = None
        try:
            yield _NodeHandle(self, name, lf_span)
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

    def close(self) -> None:
        """run 종료: root span을 닫고 Langfuse를 flush한다. flush 없이는 이벤트가 전송 안 된다."""
        self.event("run_end", f"run:{self.run_id}")
        if self._root is not None:
            try:
                self._root.end()
            except Exception:
                pass
        if self._lf is not None:
            try:
                self._lf.flush()
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
