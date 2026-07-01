"""rerun: run_replan로 새 프로필을 만든 뒤 그 프로필로 production을 돈다(1-level 커맨드)."""

from __future__ import annotations

from typer.testing import CliRunner

from reel_gen_agent import cli
from reel_gen_agent.generate.schema import RunManifest


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
