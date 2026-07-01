"""후크 생성기. 계약 정본 specs/hook-generator.md.

LLM이 유형·문구를 비결정적으로 내고, 코드가 결정론 규칙(윈도·유형 유효성·낮은 적합도
가드·A/B 변형·텍스트/비주얼 정합)을 강제한다.
"""

from __future__ import annotations

import json

from .schema import HOOK_TYPES, HookCandidate, HookRequest, HookSet
from .text_client import TextClient

_PROMPT = (
    "Role: generate {count} first-1-3-second hooks for a 20-30s vertical beauty short.\n"
    "Product: {product}. Category: {category}. Tone: {tone}. Creator: {character}. "
    "Language: {language}.\n"
    "Write hooks that fit this specific creator's persona (what she would actually say/do).\n"
    'Output raw JSON only (no markdown fences, no prose): {{"candidates": [{{'
    '"hook_type": "H1..H12", "headline": str, "bottom_caption": str, '
    '"no_text_visual": false, "visual_direction": str, "opening_beat": str, '
    '"bridge": str, "variant": "question"|"command", "rationale": str}}]}}.\n'
    "hook_type must be one of H1..H12. no_text_visual is a boolean (true/false).\n"
    "If count>=2, include exactly one question and one command variant."
)

# 선택 str 필드(None 허용)와 필수 str 필드(기본 "")를 나눠 정제한다.
_OPTIONAL_STR = ("headline", "bottom_caption")
_REQUIRED_STR = ("visual_direction", "opening_beat", "bridge", "rationale")


def _coerce_candidate(c: dict) -> dict:
    """LLM이 낸 후보 dict를 HookCandidate 스키마에 맞게 정제한다(타입 흔들림 방어)."""

    def as_bool(v: object) -> bool:
        if isinstance(v, bool):
            return v
        return str(v).strip().lower() in {"true", "1", "yes"}

    out: dict = {"hook_type": str(c.get("hook_type", "")).strip()}
    for f in _OPTIONAL_STR:
        v = c.get(f)
        out[f] = None if v is None else str(v)
    for f in _REQUIRED_STR:
        v = c.get(f)
        out[f] = "" if v is None else str(v)
    out["reinforce_overlap"] = as_bool(c.get("reinforce_overlap", False))
    out["no_text_visual"] = as_bool(c.get("no_text_visual", False))
    variant = c.get("variant")
    out["variant"] = str(variant) if variant is not None else None
    return out


def _extract_json(raw: str) -> str:
    """LLM 응답에서 JSON 오브젝트만 뽑는다. 마크다운 펜스·앞뒤 산문을 견딘다."""
    s = raw.strip()
    if s.startswith("```"):
        # ```json ... ``` 펜스 제거: 첫 줄과 마지막 펜스를 벗긴다.
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        return s[start : end + 1]
    return s


def _window(duration_sec: float) -> tuple[float, float]:
    if duration_sec >= 10:
        return (0.0, 3.0)
    return (0.0, min(2.0, duration_sec * 0.2))


def generate_hooks(request: HookRequest, client: TextClient, brief: str = "") -> HookSet:
    prompt = _PROMPT.format(
        count=request.count,
        product=request.product.name,
        category=request.category or "auto",
        tone=", ".join(request.tone) or "auto",
        character=request.character or "an attractive early-20s American beauty creator",
        language=request.language or "en",
    )
    # 스토리보드 핑퐁 피드백 등 추가 문맥이 있으면 프롬프트에 얹는다(하드코딩 아님, 문맥 주입).
    if brief:
        prompt += f"\nContext / goal and feedback to satisfy: {brief}"
    raw = client.complete(prompt, temperature=0.9)
    data = json.loads(_extract_json(raw))
    window = _window(request.duration_sec)
    candidates: list[HookCandidate] = []
    for c in data["candidates"]:
        cand = HookCandidate(**_coerce_candidate(c))  # validator가 hook_type을 검증한다
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
