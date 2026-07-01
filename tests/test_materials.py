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

    def render_panel(self, still, dur, w, h, fps, out, motion="", prompt="", generate_audio=False):
        from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend

        self.calls.append((still, dur, prompt, generate_audio))
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
    # 기본 나레이션(voiceover)이면 영상에서 말하는 느낌을 없앤다(립싱크 불일치 방지).
    assert "NOT talking" in fake.calls[0][2]
    # 씬 오디오(효과음/앰비언스)는 거의 항상 켠다(무음 영상 지양). voiceover면 "말하지 않음"
    # 지시로 씬 사운드만 나오고, 최종에서 나레이션 아래 낮게 깔린다.
    assert fake.calls[0][3] is True  # generate_audio: 씬 오디오 생성 on
    # 외모·피부 질감 같은 내용은 프롬프트로 강제하지 않는다(입력·시작 이미지에서 온다).
    assert "matte" not in fake.calls[0][2] and "attractive" not in fake.calls[0][2]
    # 편집단계 beat-cut 몽타주: 한 세그먼트를 패널 경계로 6컷으로 재분할한다.
    assert len(mats.shot_clips) == 6
    # 자막은 패널별로 6개, 구간도 타임라인에 매핑된다.
    assert len(mats.subtitle_pngs) == 6
    assert mats.subtitle_spans[-1] == [5.0, 6.0]
