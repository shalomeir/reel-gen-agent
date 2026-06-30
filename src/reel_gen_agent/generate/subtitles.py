"""자막 PNG 렌더. Pillow 위에 pilmoji로 컬러 이모지를 보존한 투명 PNG를 만든다.

자막 텍스트·타이밍은 스토리보드 패널에서 오므로 음성 인식·강제 정렬이 필요 없다.
(docs/pipeline-design.md "자막과 이모지")
"""

from __future__ import annotations

from PIL import Image, ImageFont
from pilmoji import Pilmoji


def _default_font(size: int) -> ImageFont.ImageFont:
    """기본 폰트를 요청 크기로 만든다. 구버전 Pillow는 size 인자가 없어 폴백한다."""
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def render_subtitle_png(text: str, width: int, height: int, out_path: str) -> str:
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if text:
        font = _default_font(max(28, width // 18))
        with Pilmoji(img) as p:
            tw, th = p.getsize(text, font=font)
            x = max(0, (width - tw) // 2)
            y = int(height * 0.78)
            p.text((x, y), text, fill=(255, 255, 255, 255), font=font)
    img.save(out_path)
    return out_path
