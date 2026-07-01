from reel_gen_agent.generate.cost import PRICING_AS_OF, estimate_cost
from reel_gen_agent.generate.schema import (
    NarrationLine,
    NarrationSpec,
    Objective,
    ProductionPlan,
    ProductSpec,
    ReelProfile,
    RunManifest,
    Storyboard,
    StoryboardPanel,
)


def _paid_profile():
    return ReelProfile(
        objective=Objective(goal="serum glow reel", key_message="dewy"),
        product=ProductSpec(name="Glow Serum"),
        storyboard=Storyboard(
            panels=[
                StoryboardPanel(index=0, t_start=0, t_end=2, still_image="s0.png"),
                StoryboardPanel(index=1, t_start=2, t_end=3.5, still_image="s1.png"),
            ]
        ),
        narration=NarrationSpec(
            delivery="voiceover",
            lines=[
                NarrationLine(panel_index=0, text="hello"),
                NarrationLine(panel_index=1, text="world!"),
            ],
        ),
    )


def _lines_by_label(cost):
    return {ln.label: ln for ln in cost.lines}


def test_paid_path_prices_each_backend():
    profile = _paid_profile()
    plan = ProductionPlan(
        video_model="veo-3.1-fast-generate-001",
        voice_strategy="separate_tts",
        bgm="gen",
    )
    manifest = RunManifest(panel_segments=["c0.mp4", "c1.mp4"])
    env = {"GOOGLE_CLOUD_PROJECT": "proj", "ELEVENLABS_API_KEY": "k"}

    cost = estimate_cost(profile, plan, manifest, {"passed": True}, {"gated_score": 70}, env)
    lines = _lines_by_label(cost)

    assert cost.as_of == PRICING_AS_OF
    # 스틸 2장 x $0.12 히어로
    assert lines["패널 스틸"].subtotal_usd == 0.24
    # 영상 3.5초 x $0.15 (veo fast)
    assert lines["영상 클립"].model == "veo-3.1-fast-generate-001"
    assert lines["영상 클립"].subtotal_usd == round(3.5 * 0.15, 4)
    # BGM 3.5초 x $0.06 (lyria)
    assert lines["BGM"].model == "lyria-002"
    assert lines["BGM"].subtotal_usd == round(3.5 * 0.06, 4)
    # 나레이션 eleven_v3, 11자 -> 0.011k
    assert lines["나레이션"].model == "eleven_v3"
    assert lines["나레이션"].unit == "1k자"
    # VLM 2회 x $0.02
    assert lines["품질 평가"].subtotal_usd == 0.04
    assert cost.total_usd == round(sum(ln.subtotal_usd for ln in cost.lines), 4)


def test_local_fallback_costs_nothing():
    profile = _paid_profile()
    plan = ProductionPlan(video_model="ken_burns", voice_strategy="none", bgm="none")
    manifest = RunManifest(panel_segments=["c0.mp4"])

    # rubric 비어 있음 -> use_vlm 꺼짐 -> VLM 라인 없음. bgm none, video ken_burns 로컬.
    cost = estimate_cost(profile, plan, manifest, {"passed": True}, {}, {})
    labels = {ln.label for ln in cost.lines}

    assert "영상 클립" not in labels
    assert "BGM" not in labels
    assert "나레이션" not in labels
    assert "품질 평가" not in labels
    # 스틸만 남는다(패널에 still_image가 있으므로).
    assert cost.total_usd == 0.24


def test_reel_video_override_forces_ken_burns():
    profile = _paid_profile()
    plan = ProductionPlan(video_model="veo-3.1-fast-generate-001", bgm="none")
    manifest = RunManifest(panel_segments=["c0.mp4", "c1.mp4"])

    cost = estimate_cost(profile, plan, manifest, {}, {}, {"REEL_VIDEO": "ken_burns"})
    labels = {ln.label for ln in cost.lines}
    assert "영상 클립" not in labels  # 오버라이드로 로컬 폴백 -> $0


def test_kling_reference_to_video_is_priced_by_partial_match():
    profile = _paid_profile()
    plan = ProductionPlan(
        video_model="fal-ai/kling-video/o3/pro/reference-to-video", bgm="none"
    )
    manifest = RunManifest(panel_segments=["c0.mp4"])

    cost = estimate_cost(profile, plan, manifest, {}, {}, {})
    video = next(ln for ln in cost.lines if ln.label == "영상 클립")
    assert video.subtotal_usd == round(3.5 * 0.28, 4)
