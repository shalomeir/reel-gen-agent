"""plan 페이즈 진입점. LangGraph plan 그래프를 만들고 실행한다([plan_graph.py]).

흐름: intake -> reference_seed -> character -> environment -> music -> hook <-> storyboard
(핑퐁) -> narration -> assets -> write. 각 노드는 공유 상태(PlanState)를 읽고 부분 업데이트를
돌려주며, Tracer가 노드 span을 로컬 trace(+옵션 Langfuse)에 남긴다([trace.py]).
"""

from __future__ import annotations

from pathlib import Path

from .gates import GateConfig
from .image_client import ImageClient
from .intake import intake
from .plan_graph import build_plan_graph
from .run_paths import make_run_id
from .text_client import TextClient
from .trace import Tracer


def run_planning(
    raw: str,
    outputs_root: str,
    *,
    gate: GateConfig,
    text_client: TextClient | None = None,
    image_client: ImageClient | None = None,
) -> Path:
    """입력 -> ReelProfile(plan/ 하위 JSON). plan 그래프를 컴파일해 한 번 실행한다."""
    result = intake(raw)
    if result.objective is None:
        raise ValueError("objective(영상 목적)는 필수다. 입력이 비었다.")

    # run_id는 출력 폴더 이름이자 trace run_id다(한 번만 만들어 재사용). 단독 명령은 session=run.
    run_id = make_run_id(result.objective.goal)
    tracer = Tracer(session_id=run_id, run_id=run_id)

    graph = build_plan_graph()
    final = graph.invoke(
        {
            "raw": raw,
            "outputs_root": outputs_root,
            "text_client": text_client,
            "image_client": image_client,
            "tracer": tracer,
        }
    )
    return Path(final["profile_path"])
