from PIL import Image

from reel_gen_agent.generate.subtitles import render_subtitle_png


def test_writes_rgba_png_of_frame_size(tmp_path):
    out = tmp_path / "sub.png"
    p = render_subtitle_png("Glowing skin ✨", 1080, 1920, str(out))
    img = Image.open(p)
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"


def test_empty_text_is_fully_transparent(tmp_path):
    out = tmp_path / "empty.png"
    render_subtitle_png("", 540, 960, str(out))
    img = Image.open(out).convert("RGBA")
    # 알파 최대값이 0이면 완전히 투명하다.
    assert max(px[3] for px in img.getdata()) == 0
