from PIL import Image

from reel_gen_agent.generate import materials as materials_mod
from reel_gen_agent.generate.materials import build_materials
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
        reference_images=None,
    ):
        from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend

        self.calls.append((still, dur, prompt, generate_audio, reference_images))
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
    # 씬 오디오(효과음/앰비언스)는 켠다(효과음 때문). voiceover면 오디오에 발화가 섞이지 않게
    # "발화·음성 금지, 앰비언스/효과음만"을 프롬프트에 강하게 명시한다(Veo가 제멋대로 대사를
    # 까는 걸 막는다). 실제 나레이션은 뒤 voice 노드가 넣는다.
    assert fake.calls[0][3] is True  # generate_audio: 씬 오디오 on(효과음)
    assert "no spoken words in any language" in fake.calls[0][2]  # 오디오 발화 금지
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
