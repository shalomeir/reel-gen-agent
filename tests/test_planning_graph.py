import json

import pytest

from reel_gen_agent.generate.planning_graph import run_planning
from reel_gen_agent.generate.schema import ReelProfile
from reel_gen_agent.generate.text_client import StubTextClient


def test_run_planning_writes_valid_reel_profile(tmp_path):
    cands = {
        "candidates": [
            {
                "hook_type": "H1",
                "headline": "Glow",
                "visual_direction": "macro",
                "bridge": "serum",
                "variant": "question",
            },
            {
                "hook_type": "H1",
                "headline": "Glow now",
                "visual_direction": "macro",
                "bridge": "serum",
                "variant": "command",
            },
        ]
    }
    client = StubTextClient([json.dumps(cands)])
    path = run_planning(
        "발랄한 15초 언박싱 릴. 제품: https://b/serum",
        str(tmp_path / "outputs"),
        text_client=client,
    )
    assert path.name.startswith("ReelProfile-")
    profile = ReelProfile.model_validate_json(path.read_text(encoding="utf-8"))
    assert profile.objective.goal


def test_missing_objective_raises(tmp_path):
    with pytest.raises(ValueError):
        run_planning("", str(tmp_path / "outputs"))


def test_music_runs_after_narration_last():
    # music은 확정 훅·스토리·나레이션을 보고 정하도록 plan의 마지막(narration 다음)에 온다.
    from reel_gen_agent.generate.plan_graph import build_plan_graph

    edges = {(e.source, e.target) for e in build_plan_graph().get_graph().edges}
    assert ("narration", "music") in edges
    assert ("music", "write_profile") in edges
    assert ("environment", "hook") in edges
    # 옛 배선(music이 앞)이 남아 있지 않아야 한다.
    assert ("environment", "music") not in edges
    assert ("music", "hook") not in edges
