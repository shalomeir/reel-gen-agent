from reel_gen_agent.generate.production_plan import (
    motion_for_panel,
    resolve_plan,
    segment_panels,
)
from reel_gen_agent.generate.schema import (
    NarrationSpec,
    Objective,
    ProductSpec,
    ReelProfile,
    Storyboard,
    StoryboardPanel,
)


def _profile(delivery="voiceover", panels=1, beats=None, product_locks=None) -> ReelProfile:
    ps = [
        StoryboardPanel(
            index=i,
            beat=(beats[i] if beats else None),
            product_lock=bool(product_locks[i]) if product_locks else False,
        )
        for i in range(panels)
    ]
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


def _timed_panels(n, dur=1.0):
    return [
        StoryboardPanel(index=i, t_start=i * dur, t_end=i * dur + dur) for i in range(n)
    ]


def test_segment_panels_groups_video_calls_under_max_clip():
    # 14컷 x 1초 = 14초. Veo max_clip_sec 8초면 두 세그먼트로 묶여 호출 2회.
    segs = segment_panels(_timed_panels(14), max_clip_sec=8.0, per_panel=False)
    assert len(segs) == 2
    assert segs[0] == list(range(8))
    assert segs[1] == list(range(8, 14))


def test_segment_panels_per_panel_for_ken_burns():
    segs = segment_panels(_timed_panels(3), max_clip_sec=8.0, per_panel=True)
    assert segs == [[0], [1], [2]]


def test_resolve_plan_ken_burns_segments_are_per_panel():
    plan = resolve_plan(_profile(panels=3, beats=["hook", "use", "cta"]), env={})
    assert plan.segments == [[0], [1], [2]]


def test_motion_for_panel_hook_pushes_in():
    hook = StoryboardPanel(index=0, beat="hook")
    assert motion_for_panel(hook) == "push_in"


def test_motion_for_panel_product_cut_zooms_into_product():
    # 제품 강조 컷은 항상 안쪽(제품)으로 줌인. 연속 컷은 강/약 줌인을 번갈아 경계를 살린다.
    p0 = StoryboardPanel(index=0, beat="proof", product_lock=True)
    p1 = StoryboardPanel(index=1, beat="cta", product_lock=True)
    assert motion_for_panel(p0, product_index=0) == "product_push_in"
    assert motion_for_panel(p1, product_index=1) == "zoom_in_slow"


def test_motion_for_panel_general_cuts_alternate_zoom():
    use = StoryboardPanel(index=0, beat="use")
    assert motion_for_panel(use, general_index=0) == "zoom_in_slow"
    assert motion_for_panel(use, general_index=1) == "zoom_out_slow"


def test_panel_motions_follow_beats_and_product_locks():
    beats = ["hook", "problem", "discovery", "proof", "use", "cta"]
    locks = [False, False, False, True, False, True]
    plan = resolve_plan(_profile(panels=6, beats=beats, product_locks=locks), env={})
    # hook=push_in; 제품 컷(proof/cta)=제품 줌인(강/약 교대); 일반 컷만 줌인/아웃 교대.
    assert plan.panel_motions == [
        "push_in",
        "zoom_in_slow",
        "zoom_out_slow",
        "product_push_in",
        "zoom_in_slow",
        "zoom_in_slow",
    ]
