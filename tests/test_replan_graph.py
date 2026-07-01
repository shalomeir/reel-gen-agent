"""replan 서브그래프: 정체성 노드 없이 narrative(hook->storyboard->narration->music)만 돈다."""

from __future__ import annotations

from reel_gen_agent.generate.replan_graph import build_replan_graph
from reel_gen_agent.generate.schema import (
    EnvironmentSpec,
    InputMeta,
    ModelSpec,
    MusicSpec,
    Objective,
    ProductSpec,
    StyleDimensions,
)
from reel_gen_agent.generate.trace import Tracer


def _seed_state() -> dict:
    return {
        "text_client": None,  # 결정론 경로(LLM 없이 템플릿)
        "image_client": None,
        "tracer": Tracer(session_id="t-replan", run_id="t-replan"),
        "objective": Objective(goal="show a serum glow routine"),
        "product": ProductSpec(name="serum"),
        "meta": InputMeta(),
        "style": StyleDimensions(),
        "character": ModelSpec(age="early 20s", gender="female", look="radiant creator"),
        "environment": EnvironmentSpec(location="bright indoor vanity"),
        "music": MusicSpec(),
        "delivery": "voiceover",
        "ref_voice_tone": "",
        "ref_voice_pace": "",
        "ref_hook": None,
        "cut_count": 3,
        "hook_attempts": 0,
        "hook_feedback": "",
        "style_feedback": "",
    }


def test_replan_graph_produces_narrative_only():
    graph = build_replan_graph()
    final = graph.invoke(_seed_state())
    # narrative 산출물이 모두 채워진다.
    assert final["storyboard"].panels
    assert final["narration"] is not None
    assert final["music"] is not None
    assert "narrative_arc" in final
    # 정체성은 그래프가 건드리지 않는다(들어온 그대로 나온다).
    assert final["product"].name == "serum"
    assert final["character"].look == "radiant creator"


def test_replan_regenerates_style_from_start():
    # replan은 style부터 재생성한다(빈 style로 시작해도 style 노드가 채워 준다).
    graph = build_replan_graph()
    final = graph.invoke(_seed_state())  # 입력 style은 빈 StyleDimensions
    assert final["style"].tone  # 비어 있지 않게 재생성됨
    assert final["style"].pacing


def test_replan_graph_starts_with_style():
    edges = {(e.source, e.target) for e in build_replan_graph().get_graph().edges}
    assert ("__start__", "style") in edges
    assert ("style", "hook") in edges
    assert ("style_refine", "narration") in edges
    assert ("__start__", "hook") not in edges  # 옛 배선(hook이 시작)은 없어야 한다
