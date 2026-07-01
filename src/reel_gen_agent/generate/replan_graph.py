"""replan 페이즈 LangGraph. 기존 ReelProfile에서 narrative만 다시 전개한다(specs/replan.md).

흐름: hook <-> storyboard(핑퐁) -> narration -> music -> END. plan 그래프의 narrative
노드를 그대로 재사용하며, 정체성 노드(product/character/environment)와 이미지 생성·
write는 돌지 않는다. 새 폴더·에셋 복사·key_visual 재생성·프로필 조립은 오케스트레이터
(run_replan)가 맡는다. 새 훅의 키워드는 그래프 실행 후에야 정해지기 때문이다.
"""

from __future__ import annotations

from .plan_graph import (
    PlanState,
    _hook_node,
    _music_node,
    _narration_node,
    _route_after_storyboard,
    _storyboard_node,
)


def build_replan_graph():
    """replan 페이즈 StateGraph를 컴파일한다(narrative 노드만)."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(PlanState)
    for name, fn in [
        ("hook", _hook_node),
        ("storyboard", _storyboard_node),
        ("narration", _narration_node),
        ("music", _music_node),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "hook")
    g.add_edge("hook", "storyboard")
    g.add_conditional_edges(
        "storyboard", _route_after_storyboard, {"hook": "hook", "narration": "narration"}
    )
    g.add_edge("narration", "music")
    g.add_edge("music", END)
    return g.compile()
