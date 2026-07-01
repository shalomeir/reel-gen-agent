"""execute 페이즈 진입점. LangGraph execute 그래프를 만들고 실행한다([execute_graph.py]).

흐름: load -> production_plan -> stills -> materials -> assemble -> verify -> describe ->
evaluate -> report. 각 노드 span은 Tracer가 로컬 trace(+옵션 Langfuse)에 남긴다([trace.py]).
"""

from __future__ import annotations

from .execute_graph import build_execute_graph
from .run_context import output_dir_for
from .schema import RunManifest
from .trace import Tracer


def run_production(profile_path: str, *, use_vlm: bool = True) -> RunManifest:
    """ReelProfile -> 영상 + RunManifest. execute 그래프를 컴파일해 한 번 실행한다."""
    run_id = output_dir_for(profile_path).name  # run 루트 폴더 이름 = run_id = trace run_id
    tracer = Tracer(session_id=run_id, run_id=run_id)
    graph = build_execute_graph()
    final = graph.invoke(
        {"profile_path": str(profile_path), "use_vlm": use_vlm, "tracer": tracer}
    )
    return final["manifest"]
