"""style 저술·보정(concept 노드). style은 이 시스템의 핵심 축이라 절대 비워 두지 않는다.

레퍼런스가 있으면 분석 seed가 측정 style을 채우므로 이 모듈은 no-reference 경로에서 쓴다.
- 초안(author_style, storyboard 없음): hook·story 앞에서 목적·제품·캐릭터로 예비 style을 잡아
  hook/story가 방향을 갖게 한다.
- 보정(author_style, storyboard 있음): 확정된 hook·story를 보고 style을 그에 맞게 다듬는다
  (style은 콘텐츠를 따른다).

style.hook·cut_rhythm·subtitle 등 이미 확정된 값은 보존하고, LLM은 tone/pacing/motion/
palette/realism만 채운다. LLM이 없으면 ensure_style_defaults로 결정론 기본값을 보장한다.
"""

from __future__ import annotations

import json
from pathlib import Path

from .character import character_brief
from .hook import _extract_json
from .schema import StyleDimensions
from .text_client import TextClient

# StyleDimensions가 허용하는 enum. LLM 값이 이 집합 밖이면 무시하고 기존/기본을 유지한다.
_PACING = {"fast_montage", "slow_demo", "mixed"}
_MOTION = {"still", "gentle", "dynamic"}

# 레퍼런스를 가로질러 얻은 일반 인사이트(브랜드 중립). style을 어떤 축으로 잡을지 방향을
# 주되 특정 값으로 못박지 않는다. 문서는 계속 자라므로 스냅샷을 프롬프트에 박지 않고 런타임에
# 읽는다(파일이 없으면 조용히 건너뛴다). 경로는 레포 루트 기준(개발 체크아웃에서 동작).
_INSIGHT_PATH = Path(__file__).resolve().parents[3] / "docs" / "refer-insight.md"
_insight_cache: str | None = None


def _reference_insight() -> str:
    """docs/refer-insight.md를 최선노력으로 읽어 캐시한다. 없거나 실패하면 빈 문자열."""
    global _insight_cache
    if _insight_cache is None:
        try:
            _insight_cache = _INSIGHT_PATH.read_text(encoding="utf-8").strip()
        except Exception:
            _insight_cache = ""
    return _insight_cache


def author_style(
    text_client: TextClient,
    *,
    objective,
    product,
    character,
    meta,
    base: StyleDimensions,
    storyboard=None,
    hook=None,
) -> StyleDimensions:
    """LLM으로 style 차원을 저술한다. storyboard가 오면 확정 콘텐츠 기반 '보정', 없으면 '초안'.

    base의 hook·cut_rhythm·subtitle은 그대로 두고 tone/pacing/motion/palette/realism만 채운다.
    """
    if storyboard is not None:
        stage = (
            "The hook and storyboard are now FINALIZED. Refine the visual style so it best fits "
            "THIS hook and story (style follows the content, not the other way around).\n"
        )
        beats = [p.beat or "" for p in storyboard.panels]
        hook_bits = ""
        if hook is not None:
            hook_bits = (
                f"Hook: {(hook.headline or '').strip()} | "
                f"{(hook.visual_direction or '').strip()}\n"
            )
        story_bits = f"Cuts ({len(beats)}) beats in order: {beats}\n"
    else:
        stage = (
            "Set a preliminary visual style BEFORE the hook and storyboard are written, so they "
            "have a clear direction to follow.\n"
        )
        hook_bits = ""
        story_bits = ""
    # 레퍼런스 인사이트가 있으면 방향 참고로 얹는다(값을 못박는 게 아니라 "이 축이 실제로
    # 움직인다"는 관찰이라, 기본값으로 수렴하지 말고 목적·제품에 맞게 고르라고 안내한다).
    insight = _reference_insight()
    insight_bits = (
        "Cross-reference insights (general observations, not fixed values — use as guidance for "
        "which axes to move; do not collapse to defaults, and keep authenticity over a pushy "
        f"discount tone):\n{insight}\n\n"
        if insight
        else ""
    )
    prompt = (
        "You define the visual STYLE of a one-person, product-focused vertical short-form beauty "
        "video.\n"
        f"{stage}"
        f"{insight_bits}"
        f"Goal: {objective.goal}\n"
        f"Product: {product.name}\n"
        f"Model/creator: {character_brief(character) if character else 'an early-20s creator'}\n"
        f"{hook_bits}{story_bits}"
        "Return raw JSON only:\n"
        '{"tone": ["3-5 mood adjectives"], "pacing": "fast_montage|slow_demo|mixed", '
        '"motion": "still|gentle|dynamic", "palette": ["3-5 color words or hex"], '
        '"realism": "hyper_realistic or a short realism descriptor"}\n'
        "pacing = cut frequency (many short cuts = fast_montage, few long holds = slow_demo). "
        "motion = in-shot camera motion, a separate axis from cut frequency."
    )
    raw = text_client.complete(prompt, temperature=0.6)
    data = json.loads(_extract_json(raw))
    return _apply(base, data if isinstance(data, dict) else {})


def _apply(base: StyleDimensions, data: dict) -> StyleDimensions:
    """LLM JSON을 base 위에 얹는다. 유효한 값만 반영하고 나머지는 base를 유지한다."""
    style = base.model_copy(deep=True)
    tone = data.get("tone")
    if isinstance(tone, list):
        cleaned = [str(t).strip() for t in tone if str(t).strip()]
        if cleaned:
            style.tone = cleaned[:5]
    if data.get("pacing") in _PACING:
        style.pacing = data["pacing"]
    if data.get("motion") in _MOTION:
        style.motion = data["motion"]
    palette = data.get("palette")
    if isinstance(palette, list):
        cleaned = [str(c).strip() for c in palette if str(c).strip()]
        if cleaned:
            style.palette = cleaned[:5]
    realism = data.get("realism")
    if isinstance(realism, str) and realism.strip():
        style.realism = realism.strip()
    return style


def ensure_style_defaults(style: StyleDimensions, storyboard, meta) -> StyleDimensions:
    """LLM·레퍼런스 없이도 style이 비지 않게 결정론 기본값을 채운다(핵심 축을 빈 채로 두지 않음).

    pacing은 storyboard가 있으면 컷당 평균 길이로 추정한다(짧으면 fast_montage, 길면 slow_demo).
    """
    s = style.model_copy(deep=True)
    if not s.tone:
        s.tone = ["authentic", "fresh", "glowing"]
    if not s.pacing:
        n = len(storyboard.panels) if storyboard else 0
        if n:
            avg = meta.duration_sec / n
            s.pacing = "fast_montage" if avg < 1.5 else ("slow_demo" if avg > 3.0 else "mixed")
        else:
            s.pacing = "mixed"
    if not s.motion:
        s.motion = "gentle"
    return s
