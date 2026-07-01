import pytest
from PIL import Image

from reel_gen_agent.generate.subtitles import (
    _SUBTITLE_FONT_CANDIDATES,
    LocalEmojiSource,
    _emoji_font,
    _first_existing_font_path,
    _subtitle_font,
    render_subtitle_png,
)


def test_writes_rgba_png_of_frame_size(tmp_path):
    out = tmp_path / "sub.png"
    p = render_subtitle_png("Glowing skin ✨", 1080, 1920, str(out))
    img = Image.open(p)
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"


def _has_color_pixel(img: Image.Image) -> bool:
    """채도 높은(컬러) 픽셀이 있으면 True. 텍스트는 흑백이라 컬러=이모지가 렌더된 증거."""
    rgba = img.convert("RGBA")
    for r, g, b, a in rgba.getdata():
        if a > 40 and (max(r, g, b) - min(r, g, b)) > 60:
            return True
    return False


def test_emoji_renders_in_color_offline(tmp_path):
    # 로컬 이모지 폰트가 없으면(그럼 CDN 의존) 이 테스트는 건너뛴다.
    if _emoji_font() is None:
        pytest.skip("no local color emoji font")
    out = tmp_path / "emoji.png"
    render_subtitle_png("Glow ✨💕", 1080, 1920, str(out))
    assert _has_color_pixel(Image.open(out))  # 이모지가 컬러로 그려졌다(tofu/깨짐 아님)


def test_korean_subtitle_uses_cjk_font_when_available(tmp_path):
    font_path = _first_existing_font_path(_SUBTITLE_FONT_CANDIDATES)
    if font_path is None:
        pytest.skip("no local CJK subtitle font")

    font = _subtitle_font(60)
    assert getattr(font, "path", None) == font_path

    out = tmp_path / "korean.png"
    render_subtitle_png("잠깐만요 이거 진짜 괜찮은데요 ✨", 1080, 1920, str(out))
    img = Image.open(out).convert("RGBA")
    assert max(px[3] for px in img.getdata()) > 0


def test_local_emoji_source_returns_png_bytes():
    font = _emoji_font()
    if font is None:
        pytest.skip("no local color emoji font")
    data = LocalEmojiSource(font).get_emoji("✨")
    assert data is not None and data.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"


def test_empty_text_is_fully_transparent(tmp_path):
    out = tmp_path / "empty.png"
    render_subtitle_png("", 540, 960, str(out))
    img = Image.open(out).convert("RGBA")
    # 알파 최대값이 0이면 완전히 투명하다.
    assert max(px[3] for px in img.getdata()) == 0
