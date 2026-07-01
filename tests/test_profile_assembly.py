from reel_gen_agent.generate.profile_assembly import assemble_profile, write_profile
from reel_gen_agent.generate.run_paths import profile_filename
from reel_gen_agent.generate.schema import MusicSpec, Objective, ProductSpec, ReelProfile


def test_music_audio_decisions_map_to_production_intent():
    # 음악 노드의 베드 유무·SFX 결정이 production_intent로 옮겨져야 한다(execute가 이걸 해소).
    profile = assemble_profile(
        {
            "objective": Objective(goal="asmr reel"),
            "product": ProductSpec(name="serum"),
            "music": MusicSpec(bgm="none", sfx=True),
        }
    )
    assert profile.production_intent.bgm_pref == "none"
    assert profile.production_intent.sfx_pref is True

    bed = assemble_profile(
        {
            "objective": Objective(goal="glow reel"),
            "product": ProductSpec(name="serum"),
            "music": MusicSpec(bgm="bed", sfx=False),
        }
    )
    assert bed.production_intent.bgm_pref == "gen"
    assert bed.production_intent.sfx_pref is False


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
