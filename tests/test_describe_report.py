from reel_gen_agent.generate.describe import build_upload_kit, render_upload_md
from reel_gen_agent.generate.report import build_final_report, render_report_md
from reel_gen_agent.generate.schema import (
    NodeRun,
    Objective,
    ProductionPlan,
    ProductSpec,
    ReelProfile,
    RunManifest,
    Storyboard,
    StoryboardPanel,
)


def _profile():
    return ReelProfile(
        objective=Objective(goal="serum glow reel", key_message="dewy in 15s"),
        product=ProductSpec(name="Glow Serum"),
        storyboard=Storyboard(panels=[StoryboardPanel(index=0, t_start=0, t_end=2)]),
    )


def test_upload_kit_has_title_and_outline(tmp_path):
    kit = build_upload_kit(_profile())
    assert kit.title
    assert len(kit.outline) == 1
    assert "Glow Serum" in kit.caption
    out = tmp_path / "upload.md"
    render_upload_md(kit, str(out))
    assert out.read_text(encoding="utf-8").strip()


def test_final_report_md_puts_user_input_first_and_prompts_last(tmp_path):
    profile = _profile()
    manifest = RunManifest(
        run_id="glow-20260701-101010",
        nodes=[NodeRun(name="video", prompt="serum on a table")],
        production_plan=ProductionPlan(video_model="ken_burns", voice_strategy="none"),
    )
    rep = build_final_report(
        "glow-20260701-101010", profile, manifest, {"passed": True}, {"gated_score": 71}
    )
    out = tmp_path / "report.md"
    render_report_md(rep, str(out))
    text = out.read_text(encoding="utf-8")
    assert text.index("serum glow reel") < text.index("serum on a table")
