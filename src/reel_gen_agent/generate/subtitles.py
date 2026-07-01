"""자막 PNG 렌더. Pillow 위에 pilmoji로 컬러 이모지를 보존한 투명 PNG를 만든다.

자막 텍스트·타이밍은 스토리보드 패널에서 오므로 음성 인식·강제 정렬이 필요 없다.
(docs/pipeline-design.md "자막과 이모지")

이모지는 로컬 컬러 이모지 폰트(Apple Color Emoji / Noto Color Emoji)로 렌더한다. pilmoji
기본 소스는 CDN에서 이모지 PNG를 내려받아 네트워크가 없거나 막히면 깨진다(tofu). 로컬 폰트
소스로 오프라인·결정론 렌더를 보장하고, 로컬 폰트가 없을 때만 기본(온라인) 소스로 폴백한다.
"""

from __future__ import annotations

import os
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji
from pilmoji.source import BaseSource

# 컬러 이모지 폰트 후보(순서대로 탐색). 환경변수 REEL_EMOJI_FONT로 덮어쓸 수 있다.
_EMOJI_FONT_CANDIDATES = [
    os.environ.get("REEL_EMOJI_FONT"),
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "/System/Library/Fonts/Supplemental/Apple Color Emoji.ttc",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/NotoColorEmoji.ttf",
    "/usr/local/share/fonts/NotoColorEmoji.ttf",
]


def _emoji_font() -> Any | None:
    """설치된 컬러 이모지 폰트를 연다. 없으면 None(그때만 온라인 소스로 폴백)."""
    path = next((p for p in _EMOJI_FONT_CANDIDATES if p and os.path.exists(p)), None)
    if not path:
        return None
    # Apple/Noto는 고정 비트맵 strike만 있어 임의 크기가 안 된다. 가용 strike를 차례로 시도.
    for sz in (137, 136, 96, 109, 64, 48, 32):
        try:
            return ImageFont.truetype(path, sz)
        except Exception:
            continue
    return None


class LocalEmojiSource(BaseSource):
    """로컬 컬러 이모지 폰트로 이모지를 PNG로 렌더하는 pilmoji 소스(오프라인·결정론)."""

    def __init__(self, font: Any) -> None:
        self._font = font

    def get_emoji(self, emoji: str, /) -> BytesIO | None:
        try:
            box = 176
            img = Image.new("RGBA", (box, box), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.text((box // 2, box // 2), emoji, font=self._font, embedded_color=True, anchor="mm")
            bbox = img.getbbox()
            if bbox is None:
                return None
            out = BytesIO()
            img.crop(bbox).save(out, format="PNG")
            out.seek(0)
            return out
        except Exception:
            return None

    def get_discord_emoji(self, id: int, /) -> BytesIO | None:
        return None


def _make_pilmoji(img: Any) -> Pilmoji:
    """로컬 이모지 폰트가 있으면 로컬 소스로, 없으면 기본(온라인) 소스로 Pilmoji를 만든다."""
    font = _emoji_font()
    if font is not None:
        return Pilmoji(img, source=LocalEmojiSource(font))
    return Pilmoji(img)


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
        with _make_pilmoji(img) as p:
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
