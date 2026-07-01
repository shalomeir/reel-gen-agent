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
    # BGM은 클립당 정액: 3.5초 영상 -> 1클립 x $0.04 (lyria, 초당 아님)
    assert lines["BGM"].model == "lyria-002"
    assert lines["BGM"].unit == "클립"
    assert lines["BGM"].quantity == 1
    assert lines["BGM"].subtotal_usd == 0.04
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
    plan = ProductionPlan(video_model="fal-ai/kling-video/o3/pro/reference-to-video", bgm="none")
    manifest = RunManifest(panel_segments=["c0.mp4"])

    cost = estimate_cost(profile, plan, manifest, {}, {}, {})
    video = next(ln for ln in cost.lines if ln.label == "영상 클립")
    assert video.subtotal_usd == round(3.5 * 0.28, 4)


def test_multishot_counts_all_panel_seconds_not_just_stills():
    # 멀티샷: 9패널을 2세그먼트로 묶어 스틸 2장(패널 0, 5)만 생성해도, 영상/BGM 초는
    # 전체 패널 길이(10.7초)로 잡아야 한다(still_image 유무로 과소집계 금지).
    panels = []
    for i in range(9):
        t0 = round(i * 1.19, 2)
        t1 = round((i + 1) * 1.19, 2) if i < 8 else 10.7
        still = f"still_{i}.png" if i in (0, 5) else None
        panels.append(StoryboardPanel(index=i, t_start=t0, t_end=t1, still_image=still))
    profile = ReelProfile(
        objective=Objective(goal="g", key_message="k"),
        product=ProductSpec(name="P"),
        storyboard=Storyboard(panels=panels),
    )
    plan = ProductionPlan(video_model="veo-3.1-lite-generate-001", bgm="gen")
    manifest = RunManifest(panel_segments=[f"c{i}.mp4" for i in range(9)])

    cost = estimate_cost(profile, plan, manifest, {}, {}, {"GOOGLE_CLOUD_PROJECT": "p"})
    lines = _lines_by_label(cost)

    total_sec = round(sum(max(0.5, p.t_end - p.t_start) for p in panels), 4)
    assert total_sec == 10.7  # 2.38이 아니라 전체 길이
    assert lines["영상 클립"].quantity == 10.7
    assert lines["영상 클립"].subtotal_usd == round(10.7 * 0.10, 4)
    # BGM은 초가 아니라 클립 수: 10.7초 -> 1클립(≤30초). 영상 초로 곱하지 않는다.
    assert lines["BGM"].unit == "클립"
    assert lines["BGM"].quantity == 1
    assert lines["BGM"].subtotal_usd == 0.04
    # 스틸(이미지)은 실제 생성 장수(2장)와 맞게 유지된다.
    assert lines["패널 스틸"].quantity == 2


def test_bgm_over_30s_uses_two_clips():
    # 30초를 넘는 영상은 Lyria 클립 2회(30초 단위 올림)로 잡는다.
    panels = [StoryboardPanel(index=0, t_start=0.0, t_end=45.0)]
    profile = ReelProfile(
        objective=Objective(goal="g"),
        product=ProductSpec(name="P"),
        storyboard=Storyboard(panels=panels),
    )
    plan = ProductionPlan(video_model="ken_burns", bgm="gen")
    manifest = RunManifest(panel_segments=["c0.mp4"])
    cost = estimate_cost(profile, plan, manifest, {}, {}, {"GOOGLE_CLOUD_PROJECT": "p"})
    bgm = next(ln for ln in cost.lines if ln.label == "BGM")
    assert bgm.quantity == 2  # ceil(45/30)
    assert bgm.subtotal_usd == round(2 * 0.04, 4)
