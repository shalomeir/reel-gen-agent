from unittest.mock import patch

from PIL import Image

from reel_gen_agent.generate.conformance import ConformanceReport
from reel_gen_agent.generate.production_graph import run_production
from reel_gen_agent.generate.schema import (
    InputMeta,
    Objective,
    ProductSpec,
    ReelProfile,
    Storyboard,
    StoryboardPanel,
)


def _write_profile(tmp_path):
    d = tmp_path / "demo-20260701-101010"
    d.mkdir()
    stills = []
    for i in range(2):
        s = d / f"s{i}.png"
        Image.new("RGB", (540, 960), (170, 130, 190)).save(s)
        stills.append(str(s))
    panels = [
        StoryboardPanel(
            index=i, t_start=i, t_end=i + 1, subtitle_text=f"l{i}", still_image=stills[i]
        )
        for i in range(2)
    ]
    profile = ReelProfile(
        objective=Objective(goal="demo reel"),
        product=ProductSpec(name="serum"),
        meta=InputMeta(width=540, height=960),
        storyboard=Storyboard(panels=panels),
    )
    p = d / "ReelProfile-demo-20260701-101010.json"
    p.write_text(profile.model_dump_json(), encoding="utf-8")
    return str(p), d


def test_skeleton_runs_end_to_end(tmp_path):
    profile_path, d = _write_profile(tmp_path)
    with (
        patch("reel_gen_agent.generate.execute_graph.evaluate_video") as mock_eval,
        patch("reel_gen_agent.generate.execute_graph.verify_conformance") as mock_verify,
    ):
        # 통과하는 ConformanceReport(checks=[])로 verify를 모킹한다: verify 노드가 repair
        # 판단을 위해 report.checks를 읽으므로 실제 계약을 지키는 객체를 돌려준다.
        mock_verify.return_value = ConformanceReport(checks=[], passed=True)
        mock_eval.return_value = type("E", (), {"model_dump": lambda self: {"gated_score": 70}})()
        manifest = run_production(profile_path, use_vlm=False)
    assert (d / "final.mp4").exists()
    assert (d / "report.md").exists()
    assert (d / "upload.md").exists()
    assert manifest.final_video.endswith("final.mp4")
