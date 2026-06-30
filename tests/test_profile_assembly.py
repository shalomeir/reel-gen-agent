from reel_gen_agent.generate.profile_assembly import assemble_profile, write_profile
from reel_gen_agent.generate.run_paths import profile_filename
from reel_gen_agent.generate.schema import Objective, ProductSpec, ReelProfile


def test_assemble_and_write_roundtrips(tmp_path):
    profile = assemble_profile(
        {
            "objective": Objective(goal="glow reel"),
            "product": ProductSpec(name="serum"),
        }
    )
    assert isinstance(profile, ReelProfile)
    p = write_profile(profile, tmp_path, "glow-20260701-101010")
    assert p.name == profile_filename("glow-20260701-101010")
    restored = ReelProfile.model_validate_json(p.read_text(encoding="utf-8"))
    assert restored == profile
