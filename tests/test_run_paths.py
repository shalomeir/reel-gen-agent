from datetime import datetime

from reel_gen_agent.generate.run_paths import (
    create_run_dir,
    make_run_id,
    profile_filename,
    slugify,
)


def test_slugify_basic():
    assert slugify("Glow Serum Jelly Reel!") == "glow-serum-jelly-reel"


def test_make_run_id_has_concept_and_timestamp():
    rid = make_run_id("Glow Serum", now=datetime(2026, 7, 1, 10, 10, 10))
    assert rid == "glow-serum-20260701-101010"


def test_create_run_dir_and_profile_filename(tmp_path):
    rid = "glow-serum-20260701-101010"
    d = create_run_dir(str(tmp_path), rid)
    assert d.is_dir()
    assert profile_filename(rid) == "ReelProfile-glow-serum-20260701-101010.json"
