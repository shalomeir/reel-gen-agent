"""자막 PNG 렌더. Pillow 위에 pilmoji로 컬러 이모지를 보존한 투명 PNG를 만든다.

자막 텍스트·타이밍은 스토리보드 패널에서 오므로 음성 인식·강제 정렬이 필요 없다.
(docs/pipeline-design.md "자막과 이모지")
"""

from __future__ import annotations

from typing import Any

from PIL import Image, ImageFont
from pilmoji import Pilmoji


def _default_font(size: int) -> Any:
    """기본 폰트를 요청 크기로 만든다. 구버전 Pillow는 size 인자가 없어 폴백한다.

    Pillow 버전에 따라 FreeTypeFont/ImageFont 중 하나가 오므로 반환형은 Any로 둔다.
    """
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _wrap(text: str, font: Any, max_width: int, measure) -> list[str]:
    """단어 단위로 max_width 안에 들어오도록 줄바꿈한다. 한 단어가 넘치면 그대로 둔다."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for word in words:
        cand = f"{cur} {word}".strip()
        if measure(cand, font)[0] <= max_width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


# 자막 세로 중심 위치(높이 대비). 틱톡·릴스·쇼츠는 화면 위(계정·설명)와 아래(캡션·버튼)에
# UI가 겹치므로, 위아래 끝을 피해 중앙보다 살짝 아래(안전 영역)에 둔다.
_SUBTITLE_CENTER_Y = 0.68


def render_subtitle_png(text: str, width: int, height: int, out_path: str) -> str:
    """자막을 투명 PNG로 렌더한다. 폭을 넘기면 여러 줄로 접고 안전 영역에 중앙 정렬한다."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if text:
        font = _default_font(max(28, width // 18))
        margin = int(width * 0.06)
        max_width = width - 2 * margin
        # 밝은 배경에서도 글자가 묻히지 않도록 얇은 외곽선을 두른다(그림자 아님, 작은 반경).
        stroke_w = max(2, font.size // 16 if hasattr(font, "size") else 2)
        with Pilmoji(img) as p:
            lines = _wrap(text, font, max_width, p.getsize)
            line_h = max(p.getsize(ln or "A", font=font)[1] for ln in lines)
            gap = int(line_h * 0.25)
            block_h = len(lines) * line_h + (len(lines) - 1) * gap
            # 블록을 안전 영역 중심(_SUBTITLE_CENTER_Y)에 세로 중앙 정렬한다. 위아래 끝
            # UI(계정·캡션·버튼)와 겹치지 않게 화면 끝에 붙이지 않는다.
            y = int(height * _SUBTITLE_CENTER_Y) - block_h // 2
            for line in lines:
                tw, _ = p.getsize(line, font=font)
                x = max(margin, (width - tw) // 2)
                p.text(
                    (x, y),
                    line,
                    fill=(255, 255, 255, 255),
                    font=font,
                    stroke_width=stroke_w,
                    stroke_fill=(0, 0, 0, 200),
                )
                y += line_h + gap
    img.save(out_path)
    return out_path
