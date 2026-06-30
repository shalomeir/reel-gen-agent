from reel_gen_agent.generate.run_context import new_manifest, output_dir_for
from reel_gen_agent.generate.schema import Objective, ProductSpec, ReelProfile


def _profile() -> ReelProfile:
    return ReelProfile(objective=Objective(goal="demo"), product=ProductSpec(name="serum"))


def test_output_dir_is_profile_parent(tmp_path):
    d = tmp_path / "glow-serum-20260701-101010"
    d.mkdir()
    p = d / "ReelProfile-glow-serum-20260701-101010.json"
    p.write_text(_profile().model_dump_json(), encoding="utf-8")
    assert output_dir_for(str(p)) == d


def test_new_manifest_sets_run_id_from_dirname(tmp_path):
    d = tmp_path / "glow-serum-20260701-101010"
    d.mkdir()
    p = d / "ReelProfile-x.json"
    p.write_text(_profile().model_dump_json(), encoding="utf-8")
    m = new_manifest(str(p), _profile())
    assert m.run_id == "glow-serum-20260701-101010"
    assert m.input_path == str(p)
