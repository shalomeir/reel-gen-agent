from unittest.mock import patch

from PIL import Image

from reel_gen_agent.generate import execute_graph as eg
from reel_gen_agent.generate.conformance import ConformanceReport
from reel_gen_agent.generate.production_graph import run_production
from reel_gen_agent.generate.schema import (
    AssetBible,
    CharacterProfile,
    InputMeta,
    Objective,
    ProductionPlan,
    ProductProfile,
    ProductSpec,
    ReelProfile,
    RunManifest,
    Storyboard,
    StoryboardPanel,
)


def _write_profile(tmp_path):
    d = tmp_path / "demo-20260701-101010"
    d.mkdir()
    stills = []
    for i in range(2):
        s = d / f"s{i}.png"
        Image.new("RGB", (540, 960), (170, 130, 190)).save(s)
        stills.append(str(s))
    panels = [
        StoryboardPanel(
            index=i, t_start=i, t_end=i + 1, subtitle_text=f"l{i}", still_image=stills[i]
        )
        for i in range(2)
    ]
    profile = ReelProfile(
        objective=Objective(goal="demo reel"),
        product=ProductSpec(name="serum"),
        meta=InputMeta(width=540, height=960),
        storyboard=Storyboard(panels=panels),
    )
    p = d / "ReelProfile-demo-20260701-101010.json"
    p.write_text(profile.model_dump_json(), encoding="utf-8")
    return str(p), d


def test_skeleton_runs_end_to_end(tmp_path):
    profile_path, d = _write_profile(tmp_path)
    with (
        patch("reel_gen_agent.generate.execute_graph.evaluate_video") as mock_eval,
        patch("reel_gen_agent.generate.execute_graph.verify_conformance") as mock_verify,
    ):
        # 통과하는 ConformanceReport(checks=[])로 verify를 모킹한다: verify 노드가 repair
        # 판단을 위해 report.checks를 읽으므로 실제 계약을 지키는 객체를 돌려준다.
        mock_verify.return_value = ConformanceReport(checks=[], passed=True)
        mock_eval.return_value = type("E", (), {"model_dump": lambda self: {"gated_score": 70}})()
        manifest = run_production(profile_path, use_vlm=False)
    assert (d / "final.mp4").exists()
    assert (d / "report.md").exists()
    assert (d / "upload.md").exists()
    assert manifest.final_video.endswith("final.mp4")


class _FakeTracer:
    def node(self, *args, **kwargs):
        from contextlib import nullcontext

        return nullcontext()


class _FakeImageClient:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, refs, out_path, hero=False):
        self.calls.append((prompt, refs, out_path, hero))
        Image.new("RGB", (540, 960), (180, 120, 160)).save(out_path)
        return out_path


def test_stills_node_generates_each_segment_anchor_instead_of_reusing_key_visual(
    tmp_path, monkeypatch
):
    # key_visual은 분위기 참조일 뿐이다. 세그먼트 앵커는 각 세그먼트 첫 패널 프롬프트로
    # 새로 만들어야 두 번째 세그먼트의 캐릭터/첫 컷 설정이 시작 이미지에 들어간다.
    run_dir = tmp_path / "demo-20260702-101010"
    plan_dir = run_dir / "plan"
    plan_dir.mkdir(parents=True)
    for name in ("character.png", "product.png", "key_visual.png"):
        Image.new("RGB", (540, 960), (100, 140, 180)).save(plan_dir / name)

    profile = ReelProfile(
        objective=Objective(goal="demo reel"),
        product=ProductSpec(name="serum"),
        meta=InputMeta(width=540, height=960),
        asset_bible=AssetBible(
            character=CharacterProfile(key_shot_image="character.png"),
            product=ProductProfile(hero_image="product.png"),
            key_visual="key_visual.png",
        ),
        storyboard=Storyboard(
            panels=[
                StoryboardPanel(index=0, t_start=0, t_end=1, prompt="first segment opening"),
                StoryboardPanel(index=1, t_start=1, t_end=2, prompt="middle"),
                StoryboardPanel(index=2, t_start=2, t_end=3, prompt="second segment opening"),
            ]
        ),
    )
    profile_path = plan_dir / "ReelProfile-demo-20260702-101010.json"
    profile_path.write_text(profile.model_dump_json(), encoding="utf-8")

    fake_client = _FakeImageClient()
    monkeypatch.setattr(
        "reel_gen_agent.generate.image_client.NanoBananaImageClient",
        lambda: fake_client,
    )
    monkeypatch.setenv("REEL_STILLS", "gen")

    eg._stills_node(
        {
            "profile": profile,
            "plan": ProductionPlan(segments=[[0, 1], [2]]),
            "plan_dir": plan_dir,
            "exec_dir": run_dir / "execute",
            "profile_path": str(profile_path),
            "manifest": RunManifest(),
            "tracer": _FakeTracer(),
        }
    )

    assert profile.storyboard.panels[0].still_image.endswith("still_0.png")
    assert profile.storyboard.panels[2].still_image.endswith("still_2.png")
    assert profile.storyboard.panels[2].still_image != str(plan_dir / "key_visual.png")
    assert len(fake_client.calls) == 2
    assert "second segment opening" in fake_client.calls[1][0]
