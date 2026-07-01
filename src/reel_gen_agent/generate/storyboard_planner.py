"""스토리보드 플래너 노드: 숏폼 전문가 LLM이 '스토리'를 짠다.

멀뚱한 '카메라 보고 포즈' 컷의 나열이 아니라, 영상 목적을 향해 행동·카메라 구도·효과가
서사(hook -> 전개 -> 증명 -> CTA)로 엮인 콘티를 만든다. docs/refer-insight.md,
docs/hook-insight.md의 관찰을 전문가 원칙으로 녹였다(코드가 스타일을 하드코딩하지 않고
LLM이 문맥으로 결정한다).

hook <-> storyboard 핑퐁: 이 노드는 주어진 hook을 전체 스토리에 녹여보고, 훅이 스토리에
잘 안 맞으면 hook_fits=false와 개선 힌트(hook_feedback)를 돌려준다. 그래프가 그 힌트로
hook 노드를 재호출하고 이 노드를 다시 부른다(plan_graph의 조건부 엣지).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .schema import (
    EnvironmentSpec,
    HookCandidate,
    InputMeta,
    ModelSpec,
    ProductSpec,
    StyleDimensions,
)
from .text_client import TextClient


@dataclass
class PanelPlan:
    beat: str
    shot_type: str
    camera: str
    action: str
    subtitle: str
    product_focus: bool


@dataclass
class StoryPlan:
    panels: list[PanelPlan] = field(default_factory=list)
    hook_fits: bool = True
    hook_feedback: str = ""


# 숏폼 전문가 원칙(docs/refer-insight.md, hook-insight.md 관찰을 압축). 스타일 값을 박지 않고
# "이 축이 실제로 중요하더라"는 원칙만 준다 -> LLM이 문맥에 맞게 판단한다.
_PRINCIPLES = (
    "You are a world-class short-form (Reels/TikTok/Shorts) director. Build a storyboard where "
    "the cuts, TOGETHER, tell one coherent story that serves the video's goal. Principles:\n"
    "- The first 3s hook decides retention: the opening cuts must realize the hook's visual idea, "
    "not a generic face shot.\n"
    "- Every cut must ADVANCE the story with a distinct purpose (establish, tension/problem, "
    "demonstrate/use, transformation, proof/result, payoff/CTA). No filler cuts.\n"
    "- Show meaningful ACTION and product interaction (applying, texture close-up, before/after, "
    "hands, reaction), NOT the person just posing at the camera between near-identical frames.\n"
    "- Vary shot scale and camera per cut (macro texture, close-up, medium, wide, POV, "
    "over-the-shoulder, hands detail, push-in, whip-pan) so cuts read as distinct and dynamic.\n"
    "- Keep clear product moments; a concrete where/how-to-get (CTA) lands the ending.\n"
    "- Make it DYNAMIC and high-energy: expressive faces and genuine reactions, movement and "
    "gesture, purposeful camera moves (push-in on the product or face, quick zoom, snappy whip "
    "cuts). Never blank, static posing at the camera.\n"
    "- The camera field per cut must be a concrete move (e.g. 'slow push-in', 'quick zoom to "
    "product', 'handheld orbit', 'whip pan') that the renderer will follow — not empty.\n"
    "- Keep it authentic UGC, not an infomercial; match the creator's persona and the tone."
)


def _extract_json(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


def _hook_text(hook: HookCandidate | None) -> str:
    if hook is None:
        return "none"
    bits = [hook.headline, hook.visual_direction, hook.bottom_caption]
    return " | ".join(b for b in bits if b) or "none"


def plan_story_panels(
    *,
    objective_goal: str,
    product: ProductSpec,
    character: ModelSpec,
    environment: EnvironmentSpec,
    style: StyleDimensions,
    meta: InputMeta,
    hook: HookCandidate | None,
    cut_count: int,
    text_client: TextClient,
) -> StoryPlan:
    """LLM으로 n컷 스토리보드를 짜고, 주어진 hook의 적합도를 함께 판정한다."""
    from .character import character_brief

    n = max(1, cut_count)
    affor = ", ".join(product.affordances) if product.affordances else "n/a"
    prompt = (
        f"{_PRINCIPLES}\n\n"
        f"Video goal: {objective_goal}\n"
        f"Product: {product.name} (usp: {product.usp or 'n/a'}; can show: {affor})\n"
        f"Creator (protagonist): {character_brief(character)}\n"
        f"Location: {environment.location or 'creator room'}; tone: {', '.join(style.tone) or 'natural'}\n"
        f"Duration: {meta.duration_sec:.0f}s, EXACTLY {n} cuts. Given hook: {_hook_text(hook)}\n\n"
        "First judge if the given hook can open this story well. Then design exactly "
        f"{n} cuts that tell the whole story (hook realized first, CTA last).\n"
        'Output raw JSON only (no markdown, no prose): '
        '{"hook_fits": bool, "hook_feedback": str, "panels": [{"beat": str, "shot_type": str, '
        '"camera": str, "action": str, "subtitle": str, "product_focus": bool}]}. '
        f"panels must have EXACTLY {n} items. action = the concrete on-screen action/effect for "
        "that cut (a single moment). subtitle = short keyword caption or empty string. "
        "hook_feedback = if hook_fits is false, one line on what hook would work better."
    )
    raw = text_client.complete(prompt, temperature=0.8)
    data = json.loads(_extract_json(raw))
    panels: list[PanelPlan] = []
    for p in data.get("panels", []):
        panels.append(
            PanelPlan(
                beat=str(p.get("beat") or "").strip().lower() or "b-roll",
                shot_type=str(p.get("shot_type") or "medium shot").strip(),
                camera=str(p.get("camera") or "").strip(),
                action=str(p.get("action") or "").strip(),
                subtitle=str(p.get("subtitle") or "").strip(),
                product_focus=bool(p.get("product_focus", False)),
            )
        )
    if not panels:
        raise ValueError("storyboard planner returned no panels")
    return StoryPlan(
        panels=panels,
        hook_fits=bool(data.get("hook_fits", True)),
        hook_feedback=str(data.get("hook_feedback") or "").strip(),
    )
