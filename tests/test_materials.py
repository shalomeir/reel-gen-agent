from PIL import Image

from reel_gen_agent.generate.materials import build_materials
from reel_gen_agent.generate.production_plan import resolve_plan
from reel_gen_agent.generate.schema import (
    ReelProfile,
    Objective,
    ProductSpec,
    InputMeta,
    Storyboard,
    StoryboardPanel,
)


def _profile(tmp_path):
    stills = []
    for i in range(2):
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
        for i in range(2)
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
    assert len(mats.shot_clips) == 2
    assert len(mats.subtitle_pngs) == 2
    assert (tmp_path / "run" / "panels").exists()
