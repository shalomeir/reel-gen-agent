"""rerun: run_replan로 새 프로필을 만든 뒤 그 프로필로 production을 돈다(1-level 커맨드)."""

from __future__ import annotations

from typer.testing import CliRunner

from reel_gen_agent import cli
from reel_gen_agent.generate.schema import GenerationInput, ProductSpec, RunManifest


def test_rerun_invokes_run_replan_then_produce(tmp_path, monkeypatch):
    original = tmp_path / "orig" / "plan" / "ReelProfile-orig.json"
    original.parent.mkdir(parents=True)
    original.write_text("{}", encoding="utf-8")

    new_profile = tmp_path / "new" / "plan" / "ReelProfile-new.json"
    new_profile.parent.mkdir(parents=True)
    new_profile.write_text("{}", encoding="utf-8")

    calls: dict = {}

    def fake_run_replan(profile_path, outputs_root, *, text_client, image_client):
        calls["replan_input"] = profile_path
        return new_profile

    def fake_produce(profile_path, *, use_vlm):
        calls["produced"] = profile_path
        return RunManifest(run_id="new", input_path=str(profile_path), final_video="out.mp4")

    monkeypatch.setattr(cli, "run_replan", fake_run_replan)
    monkeypatch.setattr(cli, "make_text_client", lambda: object())
    monkeypatch.setattr(cli, "_make_image_client", lambda: object())
    monkeypatch.setattr(cli, "_produce", fake_produce)

    result = CliRunner().invoke(cli.app, ["rerun", str(original)])

    assert result.exit_code == 0, result.output
    assert calls["replan_input"] == str(original)
    assert calls["produced"] == str(new_profile)


def test_execute_produces_directly(tmp_path, monkeypatch):
    profile = tmp_path / "run" / "plan" / "ReelProfile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text("{}", encoding="utf-8")

    seen: dict = {}

    def fake_produce(profile_path, *, use_vlm):
        seen["produced"] = profile_path
        return RunManifest(run_id="run", input_path=str(profile_path), final_video="out.mp4")

    monkeypatch.setattr(cli, "_produce", fake_produce)

    result = CliRunner().invoke(cli.app, ["execute", str(profile)])

    assert result.exit_code == 0, result.output
    assert seen["produced"] == str(profile)


def test_execute_help_has_no_outputs_option():
    result = CliRunner().invoke(cli.app, ["execute", "--help"])

    assert result.exit_code == 0, result.output
    assert "--outputs" not in result.output


def test_run_accepts_generation_input_json(tmp_path, monkeypatch):
    gen_input = GenerationInput(
        objective="수분 미스트를 소개하는 15초 루틴 광고",
        product=ProductSpec(
            name="BIODANCE mist",
            url="https://example.com/product",
            usp="건조한 피부에 빠른 수분감",
        ),
    )
    input_path = tmp_path / "generation_input.json"
    input_path.write_text(gen_input.model_dump_json(), encoding="utf-8")
    profile = tmp_path / "out" / "plan" / "ReelProfile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text("{}", encoding="utf-8")

    seen: dict = {}

    def fake_run_planning(raw, outputs_root, *, text_client, image_client, style_feedback=""):
        seen["planning_raw"] = raw
        return profile

    def fake_produce(profile_path, *, use_vlm):
        seen["produced"] = profile_path
        return RunManifest(run_id="run", input_path=str(profile_path), final_video="out.mp4")

    monkeypatch.setattr(cli, "run_planning", fake_run_planning)
    monkeypatch.setattr(cli, "_produce", fake_produce)

    result = CliRunner().invoke(
        cli.app,
        ["run", str(input_path), "--no-llm", "--no-images", "--no-vlm"],
    )

    assert result.exit_code == 0, result.output
    assert "수분 미스트를 소개하는 15초 루틴 광고" in seen["planning_raw"]
    assert "제품 URL: https://example.com/product" in seen["planning_raw"]
    assert seen["produced"] == str(profile)


def test_run_repairs_malformed_generation_input_with_llm(tmp_path, monkeypatch):
    input_path = tmp_path / "generation_input.json"
    input_path.write_text(
        """
        영상목적: 아마존 제품 BIODANCE 수분 미스트를 릴스 광고로 소개
        product { BIODANCE collagen mist, sprayable skincare
        url = https://example.com/biodance
        캐릭터유형: 20대 한국 여성 뷰티 크리에이터
        스타일 기대 톤: 촉촉하고 산뜻한 K-beauty 루틴, 빠른 컷
        언어값 ko
        """,
        encoding="utf-8",
    )
    profile = tmp_path / "out" / "plan" / "ReelProfile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text("{}", encoding="utf-8")

    class FakeTextClient:
        def complete(self, prompt: str, *, temperature: float = 0.9) -> str:
            if "repair rough input" in prompt:
                return """
                {
                  "objective": "BIODANCE 수분 미스트를 릴스 광고로 소개",
                  "product": "BIODANCE collagen mist, sprayable skincare",
                  "product_url": "https://example.com/biodance",
                  "character": "20대 한국 여성 뷰티 크리에이터",
                  "style": "촉촉하고 산뜻한 K-beauty 루틴, 빠른 컷",
                  "language": "ko",
                  "reference": null
                }
                """
            return '{"ok": true, "reason": ""}'

    seen: dict = {}

    def fake_run_planning(raw, outputs_root, *, text_client, image_client, style_feedback=""):
        seen["planning_raw"] = raw
        return profile

    def fake_produce(profile_path, *, use_vlm):
        seen["produced"] = profile_path
        return RunManifest(run_id="run", input_path=str(profile_path), final_video="out.mp4")

    monkeypatch.setattr(cli, "make_text_client", lambda: FakeTextClient())
    monkeypatch.setattr(cli, "run_planning", fake_run_planning)
    monkeypatch.setattr(cli, "_produce", fake_produce)

    result = CliRunner().invoke(
        cli.app,
        ["run", str(input_path), "--no-images", "--no-vlm"],
    )

    assert result.exit_code == 0, result.output
    assert "영상 목적: BIODANCE 수분 미스트를 릴스 광고로 소개" in seen["planning_raw"]
    assert "제품: BIODANCE collagen mist, sprayable skincare" in seen["planning_raw"]
    assert "제품 URL: https://example.com/biodance" in seen["planning_raw"]
    assert "캐릭터: 20대 한국 여성 뷰티 크리에이터" in seen["planning_raw"]
    assert "스타일: 촉촉하고 산뜻한 K-beauty 루틴, 빠른 컷" in seen["planning_raw"]
    assert "언어: ko" in seen["planning_raw"]
    assert seen["produced"] == str(profile)
