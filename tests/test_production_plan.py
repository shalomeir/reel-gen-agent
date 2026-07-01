from reel_gen_agent.generate.production_plan import motion_for_beat, resolve_plan
from reel_gen_agent.generate.schema import (
    NarrationSpec,
    Objective,
    ProductSpec,
    ReelProfile,
    Storyboard,
    StoryboardPanel,
)


def _profile(delivery="voiceover", panels=1, beats=None) -> ReelProfile:
    ps = [StoryboardPanel(index=i, beat=(beats[i] if beats else None)) for i in range(panels)]
    sb = Storyboard(panels=ps)
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


def test_motion_for_beat_maps_hook_and_cta():
    assert motion_for_beat("hook") == "push_in"
    assert motion_for_beat("proof") == "static"
    assert motion_for_beat("cta") == "static"


def test_motion_for_beat_general_cuts_alternate_zoom():
    assert motion_for_beat("use", 0) == "zoom_in_slow"
    assert motion_for_beat("use", 1) == "zoom_out_slow"
    assert motion_for_beat(None, 2) == "zoom_in_slow"


def test_panel_motions_follow_beats_and_alternate():
    beats = ["hook", "problem", "discovery", "proof", "use", "cta"]
    plan = resolve_plan(_profile(panels=6, beats=beats), env={})
    # hook=push_in, proof/cta=static, 일반 컷(problem/discovery/use)만 줌인/아웃 교대.
    assert plan.panel_motions == [
        "push_in",
        "zoom_in_slow",
        "zoom_out_slow",
        "static",
        "zoom_in_slow",
        "static",
    ]
