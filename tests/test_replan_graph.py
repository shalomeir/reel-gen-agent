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
