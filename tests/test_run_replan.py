"""run_replan: 정체성 고정 + narrative 재전개 + 새 폴더/에셋 복사/ key_visual 폴백."""

from __future__ import annotations

from pathlib import Path

from reel_gen_agent.generate.planning_graph import run_replan
from reel_gen_agent.generate.profile_assembly import write_profile
from reel_gen_agent.generate.schema import (
    AssetBible,
    AssetView,
    CharacterProfile,
    EnvironmentSpec,
    InputMeta,
    ModelSpec,
    MusicSpec,
    Objective,
    ProductProfile,
    ProductSpec,
    ReelProfile,
    Storyboard,
    StoryboardPanel,
    StyleDimensions,
)


def _write_original(tmp_path: Path) -> str:
    """가짜 원본 run 폴더(outputs/<run>/plan/)에 ReelProfile + 정체성 에셋 파일을 만든다."""
    plan_dir = tmp_path / "orig-run" / "plan"
    plan_dir.mkdir(parents=True)
    for name in ("char_key.png", "char_sheet.png", "prod_hero.png", "env_ref.png", "key_visual.png"):
        (plan_dir / name).write_bytes(b"PNG-STUB")
    profile = ReelProfile(
        objective=Objective(goal="show a gentle serum glow routine"),
        product=ProductSpec(name="hydra serum"),
        character=ModelSpec(age="early 20s", gender="female", look="radiant creator"),
        meta=InputMeta(),
        style=StyleDimensions(),
        narrative_arc=["hook", "use", "result"],
        asset_bible=AssetBible(
            character=CharacterProfile(
                name="creator",
                key_shot_image="char_key.png",
                sheet_image="char_sheet.png",
                views=[AssetView(name="face", image="char_sheet.png")],
            ),
            product=ProductProfile(name="hydra serum", hero_image="prod_hero.png"),
            environment=EnvironmentSpec(location="bright vanity", reference_image="env_ref.png"),
            key_visual="key_visual.png",
        ),
        storyboard=Storyboard(panels=[StoryboardPanel(index=i) for i in range(3)]),
        music=MusicSpec(),
    )
    return str(write_profile(profile, plan_dir, "orig-run"))


def test_run_replan_locks_identity_and_makes_new_folder(tmp_path):
    original = _write_original(tmp_path)
    outputs_root = str(tmp_path)

    # text/image 클라이언트 없이(결정론 + key_visual 폴백) 실행.
    new_path = run_replan(original, outputs_root, text_client=None, image_client=None)

    new_plan_dir = new_path.parent
    # 새 폴더가 원본과 다르고 실제로 생겼다.
    assert new_plan_dir.exists()
    assert new_plan_dir.resolve() != Path(original).parent.resolve()
    # 정체성 에셋 이미지가 새 plan 폴더로 복사됐다.
    assert (new_plan_dir / "char_key.png").exists()
    assert (new_plan_dir / "prod_hero.png").exists()
    assert (new_plan_dir / "env_ref.png").exists()
    # key_visual은 image_client 없으므로 원본을 복사해 폴백.
    assert (new_plan_dir / "key_visual.png").exists()

    new_profile = ReelProfile.model_validate_json(new_path.read_text(encoding="utf-8"))
    # 정체성 고정: 목적/제품/캐릭터는 원본과 동일.
    assert new_profile.objective.goal == "show a gentle serum glow routine"
    assert new_profile.product.name == "hydra serum"
    assert new_profile.character.look == "radiant creator"
    # narrative 산출물이 존재하고, 재기획 흔적이 남는다.
    assert new_profile.storyboard.panels
    assert new_profile.provenance.seeds.get("replanned_from") == original
