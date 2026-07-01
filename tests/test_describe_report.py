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


def test_upload_kit_does_not_leak_user_command(tmp_path):
    # 업로드 제목·본문은 시청자용 카피다. chat에서 친 지시문(goal/key_message)이 새면 안 된다.
    from reel_gen_agent.generate.schema import HookCandidate, StyleDimensions

    profile = ReelProfile(
        objective=Objective(goal="영상 더 밝게 만들고 자막 키워줘", key_message="자막 크게 넣어"),
        product=ProductSpec(name="Glow Serum"),
        style=StyleDimensions(
            hook=HookCandidate(
                hook_type="H1",
                headline="Want this morning glow?",
                bottom_caption="My glass skin secret",
            )
        ),
        storyboard=Storyboard(
            panels=[StoryboardPanel(index=0, t_start=0, t_end=2, subtitle_text="jelly to mist")]
        ),
    )
    kit = build_upload_kit(profile)
    out = tmp_path / "upload.md"
    render_upload_md(kit, str(out))
    text = out.read_text(encoding="utf-8")
    # 유저 지시문은 어디에도 나오면 안 된다.
    assert "영상 더 밝게" not in text
    assert "자막 키워" not in text
    assert "자막 크게" not in text
    # 제목은 훅 헤드라인, 본문엔 제품명이 들어간다.
    assert kit.title == "Want this morning glow?"
    assert "Glow Serum" in kit.caption


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
    # 예상 비용 섹션이 사용 모델 다음, 프롬프트 앞에 렌더된다.
    assert "## 예상 비용" in text
    assert rep.cost is not None
    assert text.index("## 예상 비용") < text.index("serum on a table")
    # rubric이 채워졌으니 VLM 평가 비용 라인이 잡힌다.
    assert "품질 평가" in text


def test_report_includes_plan_summary_and_video_prompt(tmp_path):
    # 캐릭터·스타일·훅·스토리보드·BGM(실제 모델)·영상 프롬프트가 리포트에 실린다.
    from reel_gen_agent.generate.schema import (
        HookCandidate,
        ModelSpec,
        MusicSpec,
        StyleDimensions,
    )

    profile = ReelProfile(
        objective=Objective(goal="glow reel"),
        product=ProductSpec(name="Glow Serum"),
        character=ModelSpec(age="mid-20s", gender="female", look="radiant dewy skin"),
        style=StyleDimensions(
            tone=["sensorial", "fresh"],
            pacing="fast_montage",
            motion="gentle",
            hook=HookCandidate(hook_type="H1", headline="Want this glow?", visual_direction="macro"),
        ),
        music=MusicSpec(mood="uplifting", style="lofi", tempo="120 bpm"),
        storyboard=Storyboard(
            panels=[StoryboardPanel(index=0, t_start=0, t_end=2, beat="hook", subtitle_text="Want this glow?")]
        ),
    )
    manifest = RunManifest(
        run_id="r",
        nodes=[NodeRun(name="visuals", prompt="[segment 0] Shot 1: macro CU of the serum")],
        production_plan=ProductionPlan(video_model="veo-3.1-fast-generate-001", bgm="gen"),
    )
    rep = build_final_report("r", profile, manifest, {"passed": True}, {})
    out = tmp_path / "report.md"
    render_report_md(rep, str(out))
    text = out.read_text(encoding="utf-8")
    assert "## 캐릭터" in text and "radiant dewy skin" in text
    assert "## 스타일" in text and "fast_montage" in text
    assert "## 훅" in text and "Want this glow?" in text
    assert "## 스토리보드" in text
    # BGM은 'gen'만이 아니라 음악 의도(무드/장르/템포)를 보인다.
    assert "무드 uplifting" in text
    # 영상 모델 프롬프트(노드별 프롬프트)가 채워진다.
    assert "Shot 1: macro CU of the serum" in text
