"""replan 페이즈 LangGraph. 기존 ReelProfile에서 narrative만 다시 전개한다(specs/replan.md).

흐름: style -> hook <-> storyboard(핑퐁) -> style_refine -> narration -> music -> END. plan
그래프의 narrative 노드를 그대로 재사용하며, 정체성 노드(product/character/environment)와
이미지 생성·write는 돌지 않는다. 새 폴더·에셋 복사·key_visual 재생성·프로필 조립은
오케스트레이터(run_replan)가 맡는다. 새 훅의 키워드는 그래프 실행 후에야 정해지기 때문이다.

replan은 style부터 재생성한다(사용자 지시: "replan은 reference 무시 style부터 재생성"). state에
provenance를 싣지 않아 style 노드가 no-reference(LLM 저술) 경로를 타므로, 이전 run의 style을
그대로 복사해 판박이가 되던 문제가 풀린다. 초안 style이 hook·story를 이끌고, 핑퐁이 끝나면
style_refine이 확정된 hook·story를 극대화하도록 style을 다시 다듬는다(plan과 동일한 두 접점).
"""

from __future__ import annotations

from .plan_graph import (
    PlanState,
    _hook_node,
    _music_node,
    _narration_node,
    _route_after_storyboard,
    _storyboard_node,
    _style_node,
    _style_refine_node,
)


def build_replan_graph():
    """replan 페이즈 StateGraph를 컴파일한다(style + narrative 노드)."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(PlanState)
    for name, fn in [
        ("style", _style_node),
        ("hook", _hook_node),
        ("storyboard", _storyboard_node),
        ("style_refine", _style_refine_node),
        ("narration", _narration_node),
        ("music", _music_node),
    ]:
        g.add_node(name, fn)
    # style 초안이 hook·story를 이끌고, 핑퐁 종료(forward) 뒤 style_refine이 보정한다.
    g.add_edge(START, "style")
    g.add_edge("style", "hook")
    g.add_edge("hook", "storyboard")
    g.add_conditional_edges(
        "storyboard", _route_after_storyboard, {"hook": "hook", "forward": "style_refine"}
    )
    g.add_edge("style_refine", "narration")
    g.add_edge("narration", "music")
    g.add_edge("music", END)
    return g.compile()
