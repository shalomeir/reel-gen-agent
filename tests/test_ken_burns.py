from PIL import Image

from reel_gen_agent.analysis.media_probe import probe_container
from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend


def _still(tmp_path):
    p = tmp_path / "still.png"
    Image.new("RGB", (1080, 1920), (200, 120, 160)).save(p)
    return str(p)


def test_ken_burns_makes_clip_of_requested_duration(tmp_path):
    out = tmp_path / "clip.mp4"
    KenBurnsBackend().render_panel(_still(tmp_path), 2.0, 1080, 1920, 30, str(out))
    meta = probe_container(str(out))
    assert out.exists()
    assert meta.duration_sec is not None
    assert abs(meta.duration_sec - 2.0) < 0.3
    # probe_container는 해상도를 "WxH" 문자열로 돌려준다.
    assert meta.resolution == "1080x1920"
