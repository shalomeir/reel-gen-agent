from PIL import Image

from reel_gen_agent.analysis.media_probe import probe_container
from reel_gen_agent.generate.assemble import assemble
from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend
from reel_gen_agent.generate.schema import InputMeta, Materials


def _clip(tmp_path, name, dur):
    still = tmp_path / f"{name}.png"
    Image.new("RGB", (540, 960), (180, 140, 200)).save(still)
    out = tmp_path / f"{name}.mp4"
    KenBurnsBackend().render_panel(str(still), dur, 540, 960, 30, str(out))
    return str(out)


def test_assemble_concats_to_expected_duration(tmp_path):
    mats = Materials(shot_clips=[_clip(tmp_path, "a", 1.0), _clip(tmp_path, "b", 1.0)])
    out = tmp_path / "final.mp4"
    assemble(mats, InputMeta(width=540, height=960), str(out))
    meta = probe_container(str(out))
    assert out.exists()
    assert meta.duration_sec is not None
    assert abs(meta.duration_sec - 2.0) < 0.4
    assert meta.resolution == "540x960"
