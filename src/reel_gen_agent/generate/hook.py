"""후크 생성기. 계약 정본 specs/hook-generator.md.

LLM이 유형·문구를 비결정적으로 내고, 코드가 결정론 규칙(윈도·유형 유효성·낮은 적합도
가드·A/B 변형·텍스트/비주얼 정합)을 강제한다.
"""

from __future__ import annotations

import json

from .schema import HOOK_TYPES, HookCandidate, HookRequest, HookSet
from .text_client import TextClient

_PROMPT = (
    "역할: 20~30초 세로 뷰티 숏폼의 첫 1~3초 후크 {count}개를 생성한다.\n"
    "제품: {product}. 카테고리: {category}. 톤: {tone}.\n"
    "출력: JSON {{\"candidates\": [{{hook_type, headline, bottom_caption, "
    "no_text_visual, visual_direction, opening_beat, bridge, variant, rationale}}]}}.\n"
    "유형은 H1~H12 중에서 고른다. count>=2면 질문형·명령형을 섞는다."
)


def _window(duration_sec: float) -> tuple[float, float]:
    if duration_sec >= 10:
        return (0.0, 3.0)
    return (0.0, min(2.0, duration_sec * 0.2))


def generate_hooks(request: HookRequest, client: TextClient) -> HookSet:
    prompt = _PROMPT.format(
        count=request.count,
        product=request.product.name,
        category=request.category or "auto",
        tone=", ".join(request.tone) or "auto",
    )
    raw = client.complete(prompt, temperature=0.9)
    data = json.loads(raw)
    window = _window(request.duration_sec)
    candidates: list[HookCandidate] = []
    for c in data["candidates"]:
        cand = HookCandidate(**c)  # validator가 hook_type을 검증한다
        cand.window_sec = window
        fit = HOOK_TYPES[cand.hook_type]["product_fit"]
        if fit == "low" and not (cand.bridge or "").strip():
            raise ValueError(f"low-fit hook {cand.hook_type} requires non-empty bridge")
        if cand.no_text_visual:
            cand.headline = None
            cand.bottom_caption = None
            if not cand.visual_direction.strip():
                raise ValueError("no_text_visual requires visual_direction")
        candidates.append(cand)
    if request.count >= 2:
        variants = {c.variant for c in candidates}
        if not ({"question", "command"} <= variants):
            raise ValueError("count>=2 must include a question and a command variant")
    return HookSet(candidates=candidates, request=request)
