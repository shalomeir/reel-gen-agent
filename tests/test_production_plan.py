from reel_gen_agent.generate.production_plan import resolve_plan
from reel_gen_agent.generate.schema import (
    ReelProfile,
    Objective,
    ProductSpec,
    Storyboard,
    StoryboardPanel,
    NarrationSpec,
)


def _profile(delivery="voiceover", panels=1) -> ReelProfile:
    sb = Storyboard(panels=[StoryboardPanel(index=i) for i in range(panels)])
    return ReelProfile(
        objective=Objective(goal="demo"),
        product=ProductSpec(name="serum"),
        storyboard=sb,
        narration=NarrationSpec(delivery=delivery),
    )


def test_no_video_key_falls_back_to_ken_burns():
    plan = resolve_plan(_profile(), env={})
    assert plan.video_model == "ken_burns"
    assert plan.panel_renderers == ["ken_burns"]
    assert any("ken_burns" in f for f in plan.fallbacks_applied)


def test_voiceover_is_default_voice_strategy():
    plan = resolve_plan(_profile(delivery="voiceover"), env={})
    assert plan.voice_strategy == "separate_tts"


def test_delivery_none_means_no_voice():
    plan = resolve_plan(_profile(delivery="none"), env={})
    assert plan.voice_strategy == "none"


def test_on_camera_multicut_without_kling_downgrades_to_voiceover():
    plan = resolve_plan(_profile(delivery="on_camera", panels=3), env={})
    assert plan.voice_strategy == "separate_tts"
    assert any("on_camera" in f for f in plan.fallbacks_applied)
