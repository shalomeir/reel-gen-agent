from PIL import Image

from reel_gen_agent.generate import materials as materials_mod
from reel_gen_agent.generate.materials import _fit_panel_durs, build_materials
from reel_gen_agent.generate.production_plan import resolve_plan
from reel_gen_agent.generate.schema import (
    InputMeta,
    Objective,
    ProductionPlan,
    ProductSpec,
    ReelProfile,
    Storyboard,
    StoryboardPanel,
)


def _profile(tmp_path, n=2):
    stills = []
    for i in range(n):
        s = tmp_path / f"s{i}.png"
        Image.new("RGB", (540, 960), (160, 120, 180)).save(s)
        stills.append(str(s))
    panels = [
        StoryboardPanel(
            index=i,
            t_start=i * 1.0,
            t_end=i * 1.0 + 1.0,
            subtitle_text=f"line {i}",
            still_image=stills[i],
        )
        for i in range(n)
    ]
    return ReelProfile(
        objective=Objective(goal="demo"),
        product=ProductSpec(name="serum"),
        meta=InputMeta(width=540, height=960),
        storyboard=Storyboard(panels=panels),
    )


def test_build_materials_makes_a_clip_and_subtitle_per_panel(tmp_path):
    profile = _profile(tmp_path)
    plan = resolve_plan(profile, env={})  # ken_burns
    mats = build_materials(profile, plan, str(tmp_path / "run"))
    assert len(mats.shot_clips) == 2  # ken_burns: 패널당 세그먼트 1개
    assert len(mats.subtitle_pngs) == 2
    assert len(mats.subtitle_spans) == 2
    # 자막 구간이 패널 타임라인과 맞는다.
    assert mats.subtitle_spans[0] == [0.0, 1.0]
    assert mats.subtitle_spans[1] == [1.0, 2.0]
    assert (tmp_path / "run" / "panels").exists()


class _FakeVeo:
    """호출 횟수만 세는 가짜 영상 백엔드. 앵커 스틸을 그대로 켄 번스로 렌더한다."""

    def __init__(self):
        self.calls = []

    def render_panel(
        self, still, dur, w, h, fps, out, motion="", prompt="", generate_audio=False,
        reference_images=None, character_ref=None, product_ref=None,
    ):
        from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend

        # 기존 인덱스 유지: [0]still [2]prompt [3]generate_audio [4]reference_images,
        # 뒤에 [5]character_ref [6]product_ref를 덧붙인다.
        self.calls.append(
            (still, dur, prompt, generate_audio, reference_images, character_ref, product_ref)
        )
        return KenBurnsBackend().render_panel(still, dur, w, h, fps, out, motion=motion)


def test_video_path_calls_backend_once_per_segment(tmp_path, monkeypatch):
    # 6컷(각 1초) = 6초 릴. Veo max_clip_sec 8초면 한 세그먼트로 묶여 호출 1회여야 한다.
    profile = _profile(tmp_path, n=6)
    fake = _FakeVeo()
    monkeypatch.setattr(materials_mod, "_video_backend", lambda plan: fake)
    plan = ProductionPlan(video_model="veo-3.1-fast-generate-001", segments=[[0, 1, 2, 3, 4, 5]])
    mats = build_materials(profile, plan, str(tmp_path / "run"))
    assert len(fake.calls) == 1  # ≤15초 = 영상 모델 호출 1회(세그먼트 1개)
    # 멀티샷 프롬프트에 샷 리스트가 들어간다.
    assert "Shot 1:" in fake.calls[0][2] and "Shot 6:" in fake.calls[0][2]
    # 기본 나레이션(voiceover/none)이면 영상에서 말하는 느낌을 없앤다(립싱크 불일치 방지).
    assert "NOT talking" in fake.calls[0][2]
    # voiceover(비발화)면 영상 모델 오디오 생성을 끈다(Kling이 제 배경음악을 크게 깔아 우리
    # BGM과 충돌하는 걸 막는다). BGM·SFX는 별도 노드가, 나레이션은 voice 노드가 넣는다.
    assert fake.calls[0][3] is False  # generate_audio: off(비발화)
    # 오디오를 꺼도 '말하는 느낌'은 시각적으로 없애야 하므로 비발화 지시는 유지한다.
    assert "no spoken words in any language" in fake.calls[0][2]
    # 외모·피부 질감 같은 내용은 프롬프트로 강제하지 않는다(입력·시작 이미지에서 온다).
    assert "matte" not in fake.calls[0][2] and "attractive" not in fake.calls[0][2]
    # 편집단계 beat-cut 몽타주: 한 세그먼트를 패널 경계로 6컷으로 재분할한다.
    assert len(mats.shot_clips) == 6
    # 자막은 패널별로 6개, 구간도 타임라인에 매핑된다.
    assert len(mats.subtitle_pngs) == 6
    assert mats.subtitle_spans[-1] == [5.0, 6.0]


def test_video_segments_start_from_their_own_anchor_stills(tmp_path, monkeypatch):
    # 세그먼트 2는 세그먼트 1의 마지막 프레임이 아니라 자기 첫 패널의 앵커 스틸로 시작해야
    # 한다. 그래야 두 번째 세그먼트 첫 컷 설정과 캐릭터 reference가 함께 반영된다.
    profile = _profile(tmp_path, n=4)
    fake = _FakeVeo()
    monkeypatch.setattr(materials_mod, "_video_backend", lambda plan: fake)
    plan = ProductionPlan(
        video_model="veo-3.1-fast-generate-001",
        segments=[[0, 1], [2, 3]],
    )

    build_materials(profile, plan, str(tmp_path / "run"))

    assert len(fake.calls) == 2
    assert fake.calls[0][0] == profile.storyboard.panels[0].still_image
    assert fake.calls[1][0] == profile.storyboard.panels[2].still_image
    assert not (tmp_path / "run" / "panels" / "lastframe_0.png").exists()


def test_integrated_speech_directive_allows_lipsync(tmp_path, monkeypatch):
    # 온카메라 발화(integrated)면 오디오도 켜고, 발화 금지 문구 대신 립싱크로 말하게 한다.
    profile = _profile(tmp_path, n=2)
    fake = _FakeVeo()
    monkeypatch.setattr(materials_mod, "_video_backend", lambda plan: fake)
    plan = ProductionPlan(
        video_model="veo-3.1-fast-generate-001",
        voice_strategy="integrated",
        segments=[[0, 1]],
    )
    build_materials(profile, plan, str(tmp_path / "run"))
    assert fake.calls[0][3] is True  # integrated: generate_audio on
    # integrated는 립싱크로 말한다 -> "발화 금지"가 아니라 "말한다" 지시.
    assert "lip-sync" in fake.calls[0][2]
    assert "no spoken words in any language" not in fake.calls[0][2]


def test_integrated_feeds_scripted_dialogue_and_language(tmp_path, monkeypatch):
    # integrated면 스크립트 노드가 만든 대사를 해당 샷에 붙이고, 언어(기본 영어)를 못박는다.
    from reel_gen_agent.generate.schema import NarrationLine, NarrationSpec

    profile = _profile(tmp_path, n=2)
    profile.narration = NarrationSpec(
        delivery="on_camera",
        lines=[NarrationLine(panel_index=0, text="You need to try this serum.")],
    )
    fake = _FakeVeo()
    monkeypatch.setattr(materials_mod, "_video_backend", lambda plan: fake)
    plan = ProductionPlan(
        video_model="veo-3.1-fast-generate-001",
        voice_strategy="integrated",
        segments=[[0, 1]],
    )
    build_materials(profile, plan, str(tmp_path / "run"))
    prompt = fake.calls[0][2]
    # 지정 언어(영어) 발화를 못박는다.
    assert "in English only" in prompt
    # 컷 0의 실제 대사가 그 샷에 붙는다.
    assert 'The person says in English: "You need to try this serum."' in prompt


def test_lang_name_defaults_to_english():
    from reel_gen_agent.generate.materials import _lang_name

    assert _lang_name(None) == "English"
    assert _lang_name("en") == "English"
    assert _lang_name("ko") == "Korean"


def test_build_visuals_captures_video_prompts(tmp_path, monkeypatch):
    # 리포트 "노드별 프롬프트"용으로 세그먼트별 영상 프롬프트를 모아 돌려준다.
    from reel_gen_agent.generate.materials import build_visuals

    profile = _profile(tmp_path, n=2)
    fake = _FakeVeo()
    monkeypatch.setattr(materials_mod, "_video_backend", lambda plan: fake)
    plan = ProductionPlan(video_model="veo-3.1-fast-generate-001", segments=[[0, 1]])
    v = build_visuals(profile, plan, str(tmp_path / "run"))
    assert len(v.prompts) == 1  # 세그먼트 1개
    assert "segment 0" in v.prompts[0]
    assert "Shot 1:" in v.prompts[0]


def test_ref2v_keeps_hook_cut_and_continuous_rest(tmp_path, monkeypatch):
    # ref2v 단일 세그먼트: 한 번에 뽑은 매끄러운 모션이라 훅 컷만 별도로 살리고 나머지는 원본
    # 모션 통짜로 둔다 -> 패널이 3개여도 clips는 훅+통짜 2개. 자막은 패널별로 유지된다.
    from reel_gen_agent.generate.materials import build_visuals

    profile = _profile(tmp_path, n=3)
    profile.storyboard.panels[0].beat = "hook"
    fake = _FakeVeo()
    monkeypatch.setattr(materials_mod, "_video_backend", lambda plan: fake)
    plan = ProductionPlan(
        video_model="fal-ai/kling-video/o3/standard/reference-to-video",
        segments=[[0, 1, 2]],
    )
    v = build_visuals(profile, plan, str(tmp_path / "run"))
    assert len(v.shot_clips) == 2  # 훅 컷 + 나머지 통짜
    assert v.segment_sizes == [2]  # 단일 세그먼트
    assert len(v.subtitle_pngs) == 3  # 자막은 패널별 유지
    assert len(v.subtitle_spans) == 3


def test_i2v_subcuts_extract_increasing_time_ranges(tmp_path, monkeypatch):
    # 회귀 방지: i2v beat-cut은 세그먼트의 서로 다른 시간 구간을 잘라야 한다. local이 안 오르면
    # 모든 서브컷이 [0, d] 같은 첫 구간만 반복 추출해 같은 컷이 반복된다(편집 버그).
    from reel_gen_agent.generate import materials as mm
    from reel_gen_agent.generate.materials import build_visuals

    starts: list[float] = []
    real = mm._extract_subcut

    def _spy(seg_clip, start, dur, *a, **k):
        starts.append(round(start, 3))
        return real(seg_clip, start, dur, *a, **k)

    monkeypatch.setattr(mm, "_extract_subcut", _spy)
    profile = _profile(tmp_path, n=4)
    fake = _FakeVeo()
    monkeypatch.setattr(mm, "_video_backend", lambda plan: fake)
    plan = ProductionPlan(
        video_model="fal-ai/kling-video/o3/standard/image-to-video",
        segments=[[0, 1, 2, 3]],
    )
    build_visuals(profile, plan, str(tmp_path / "run"))
    # 4컷 x 1초 -> 시작 오프셋이 0,1,2,3으로 증가해야 한다(전부 0이면 버그).
    assert starts == [0.0, 1.0, 2.0, 3.0]


def test_i2v_keeps_per_panel_beat_cuts(tmp_path, monkeypatch):
    # i2v(비 ref2v)는 기존대로 패널별 beat-cut으로 쪼갠다(3패널 단일 세그먼트 -> 3 clips).
    from reel_gen_agent.generate.materials import build_visuals

    profile = _profile(tmp_path, n=3)
    fake = _FakeVeo()
    monkeypatch.setattr(materials_mod, "_video_backend", lambda plan: fake)
    plan = ProductionPlan(
        video_model="fal-ai/kling-video/o3/standard/image-to-video",
        segments=[[0, 1, 2]],
    )
    v = build_visuals(profile, plan, str(tmp_path / "run"))
    assert len(v.shot_clips) == 3  # 패널별 beat-cut


def test_reference_to_video_passes_character_and_product_as_elements(tmp_path, monkeypatch):
    # reference-to-video는 인물·제품 정체성을 elements(character_ref/product_ref)로 넘기고,
    # key_visual은 스타일 참조(reference_images=image_urls)로 넘긴다. 제품은 제품 컷이 있을 때만.
    from reel_gen_agent.generate.materials import build_visuals

    profile = _profile(tmp_path, n=2)
    profile.storyboard.panels[0].product_lock = False
    profile.storyboard.panels[1].product_lock = True  # 세그먼트에 제품 컷이 있음
    fake = _FakeVeo()
    monkeypatch.setattr(materials_mod, "_video_backend", lambda plan: fake)
    # ref2v는 단일 세그먼트라 두 패널이 한 호출로 묶인다.
    plan = ProductionPlan(
        video_model="fal-ai/kling-video/o3/standard/reference-to-video",
        segments=[[0, 1]],
    )
    build_visuals(
        profile, plan, str(tmp_path / "run"),
        character_image="char.png", product_image="prod.png", key_visual="kv.png",
    )
    call = fake.calls[0]
    assert call[5] == "char.png"  # character_ref (element)
    assert call[6] == "prod.png"  # product_ref (element, 제품 컷 있음)
    assert call[4] == ["kv.png"]  # reference_images = key_visual (style/image_urls)


def test_reference_to_video_omits_product_element_without_product_cut(tmp_path, monkeypatch):
    from reel_gen_agent.generate.materials import build_visuals

    profile = _profile(tmp_path, n=2)
    for p in profile.storyboard.panels:
        p.product_lock = False  # 제품 컷 없음
    fake = _FakeVeo()
    monkeypatch.setattr(materials_mod, "_video_backend", lambda plan: fake)
    plan = ProductionPlan(
        video_model="fal-ai/kling-video/o3/standard/reference-to-video",
        segments=[[0, 1]],
    )
    build_visuals(
        profile, plan, str(tmp_path / "run"),
        character_image="char.png", product_image="prod.png", key_visual="kv.png",
    )
    assert fake.calls[0][5] == "char.png"  # 캐릭터는 항상
    assert fake.calls[0][6] is None  # 제품 컷이 없으면 제품 element는 뺀다


# --- 서브컷 길이를 실제 클립 안으로 맞추기(프리즈+세그먼트 누락 방지) --------------------


def test_fit_panel_durs_no_change_when_clip_long_enough():
    # 실제 클립(avail)이 계획 합 이상이면 원본 그대로. avail=None(폴백 ken_burns)도 그대로.
    planned = [1.2, 1.167, 1.2]
    assert _fit_panel_durs(planned, None) == planned
    assert _fit_panel_durs(planned, 5.0) == planned
    assert _fit_panel_durs(planned, sum(planned)) == planned


def test_fit_panel_durs_clamps_last_to_real_clip_end():
    # avail이 계획 합보다 짧으면 마지막 패널을 실제 클립 끝에 딱 맞춘다(비디오/오디오 함께 종료).
    planned = [3.0, 3.0, 3.0]  # 합 9.0
    out = _fit_panel_durs(planned, 7.0)
    assert out[0] == 3.0
    assert out[1] == 3.0
    assert abs(out[2] - 1.0) < 1e-9  # 7 - 6 = 1
    assert abs(sum(out) - 7.0) < 1e-9  # 실제 클립을 넘지 않는다


def test_fit_panel_durs_drops_panels_past_clip_end():
    # 남은 실제 영상이 없으면 이후 패널은 0으로(서브컷을 만들지 않아 프리즈 꼬리가 없다).
    planned = [3.0, 3.0, 3.0]
    out = _fit_panel_durs(planned, 3.02)  # 첫 패널만 실려야
    assert abs(out[0] - 3.0) < 1e-9
    assert out[1] == 0.0 and out[2] == 0.0
    assert sum(out) <= 3.02 + 1e-9
