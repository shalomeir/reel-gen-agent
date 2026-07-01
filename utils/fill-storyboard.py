#!/usr/bin/env python
"""기존 ReelProfile에 storyboard(콘티)를 채운다.

컷 경계는 결정론 레이어(PySceneDetect)로 직접 검출해 패널 타이밍을 고정하고, 컷별
콘티 내용(beat/shot/camera/프롬프트/자막/렌더러)만 Gemini 멀티모달 1콜로 채운다.
레퍼런스 영상을 충실히 재구성하는 방향이라, 패널 수는 실제 컷 수에 맞춘다.

실행:
    .venv/bin/python utils/fill-storyboard.py <ReelProfile.json> <video.mp4>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from reel_gen_agent.analysis.cut_detector import detect_cuts
from reel_gen_agent.analysis.gemini_client import run_multimodal
from reel_gen_agent.analysis.media_probe import probe_container
from reel_gen_agent.generate.schema import ReelProfile, Storyboard, StoryboardPanel

REPO_ROOT = Path(__file__).resolve().parents[1]

ALLOWED_RENDERERS = {"i2v", "ken_burns", "canvas"}
ALLOWED_BEATS = (
    "hook",
    "problem",
    "discovery",
    "use",
    "reaction",
    "proof",
    "cta",
)


# --- Gemini 콘티 스키마 --------------------------------------------------------


class PanelDraft(BaseModel):
    """컷 한 개의 콘티. 타이밍/인덱스는 코드가 컷 경계로 채우므로 여기엔 없다."""

    beat: str = ""  # hook / problem / discovery / use / reaction / proof / cta
    shot_type: str = ""  # wide / medium / macro CU ...
    camera: str = ""  # handheld / locked-off / push-in ...
    subject_lock: bool = True  # 캐릭터 에셋 참조
    product_lock: bool = False  # 제품 에셋 참조
    environment_lock: bool = True  # 환경 에셋 참조
    prompt: str = ""  # 패널 스틸 생성 프롬프트(잠근 에셋을 참조해 묘사)
    subtitle_text: str = ""  # 이 컷에 깔리는 자막(없으면 빈 문자열)
    cta_text: str = ""  # CTA 컷이면 행동유도 문구
    renderer: str = "i2v"  # i2v / ken_burns / canvas


class StoryboardPlan(BaseModel):
    global_prompt: str = ""  # 모든 컷에 흐르는 공통 맥락
    panels: list[PanelDraft] = Field(default_factory=list)


def _segments(timestamps: list[float], duration: float) -> list[tuple[float, float]]:
    """컷 경계 타임스탬프를 [start, end] 구간 리스트로 바꾼다."""
    bounds = [0.0] + [t for t in timestamps if 0.0 < t < duration] + [duration]
    bounds = sorted(set(round(b, 3) for b in bounds))
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def _build_prompt(rp: ReelProfile, segments: list[tuple[float, float]]) -> str:
    n = len(segments)
    seg_lines = "\n".join(
        f"  panel {i}: {s:.2f}s - {e:.2f}s ({e - s:.2f}s)"
        for i, (s, e) in enumerate(segments)
    )
    subs = rp.style.subtitle
    return (
        "You are reconstructing the shot-by-shot storyboard (conti) of a short-form "
        "vertical product video by watching it. Return EXACTLY "
        f"{n} panels in chronological order, one per cut segment below. Stay faithful "
        "to what actually happens on screen in each window.\n\n"
        f"Cut segments (fill one panel per segment, same order):\n{seg_lines}\n\n"
        f"Product (locked asset): {rp.product.name} - {rp.product.packaging_desc or ''}\n"
        f"Character (locked asset): {rp.character.look or 'on-camera person'}\n"
        f"Narrative arc: {', '.join(rp.narrative_arc)}\n"
        f"Palette: {', '.join(rp.style.palette[:6])}\n"
        f"Pacing: {rp.style.pacing}; cut rhythm: {rp.style.cut_rhythm.pattern}\n\n"
        "For each panel set:\n"
        f"- beat: one of {', '.join(ALLOWED_BEATS)}.\n"
        "- shot_type: e.g. wide / medium / macro CU / close-up.\n"
        "- camera: e.g. handheld / locked-off / push-in / tilt.\n"
        "- subject_lock/product_lock/environment_lock: true if that asset appears.\n"
        "- prompt: an image-generation prompt for this panel's still that references "
        "the locked character and/or product so they stay consistent across cuts.\n"
        "- subtitle_text: the on-screen caption shown in this window, else empty.\n"
        "- cta_text: only for a final call-to-action cut, else empty.\n"
        f"- renderer: one of {', '.join(sorted(ALLOWED_RENDERERS))} "
        "(i2v for motion shots, ken_burns for product/text stills, canvas for pure "
        "text cards).\n"
        "Also set global_prompt: one shared style line for every shot.\n"
        f"On-screen captions observed in analysis (use as hints): {subs.text if hasattr(subs, 'text') else ''}\n"
        "Return JSON only."
    )


def _to_panels(plan: StoryboardPlan, segments: list[tuple[float, float]]) -> list[StoryboardPanel]:
    """드래프트 패널을 컷 타이밍에 매핑해 StoryboardPanel로 만든다."""
    panels: list[StoryboardPanel] = []
    for i, (start, end) in enumerate(segments):
        draft = plan.panels[i] if i < len(plan.panels) else PanelDraft()
        beat = draft.beat.strip().lower()
        renderer = draft.renderer.strip().lower()
        panels.append(
            StoryboardPanel(
                index=i,
                beat=beat if beat in ALLOWED_BEATS else None,
                t_start=start,
                t_end=end,
                shot_type=draft.shot_type or None,
                camera=draft.camera or None,
                subject_lock=draft.subject_lock,
                product_lock=draft.product_lock,
                environment_lock=draft.environment_lock,
                prompt=draft.prompt or None,
                subtitle_text=draft.subtitle_text or None,
                cta_text=draft.cta_text or None,
                renderer=renderer if renderer in ALLOWED_RENDERERS else "i2v",
            )
        )
    return panels


def fill(reelprofile_path: Path, video: Path) -> None:
    rp = ReelProfile.model_validate_json(reelprofile_path.read_text(encoding="utf-8"))

    container = probe_container(str(video))
    cut = detect_cuts(str(video))
    duration = container.duration_sec or rp.meta.duration_sec
    segments = _segments(cut.timestamps, duration)
    print(f"[cuts] {len(segments)} segments over {duration:.2f}s", file=sys.stderr)

    prompt = _build_prompt(rp, segments)
    plan = run_multimodal(
        str(video),
        duration,
        StoryboardPlan,
        prompt,
        prompt,
        log_prefix="storyboard",
    )
    if plan is None:
        print("[storyboard] Gemini 실패 - 타이밍만 채운 패널로 진행", file=sys.stderr)
        plan = StoryboardPlan()

    panels = _to_panels(plan, segments)
    rp.storyboard = Storyboard(
        global_prompt=plan.global_prompt or None,
        panels=panels,
    )

    reelprofile_path.write_text(
        rp.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"[done] {reelprofile_path}  ({len(panels)} panels, "
        f"global_prompt={'set' if rp.storyboard.global_prompt else 'none'})",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="기존 ReelProfile에 storyboard 콘티를 채운다."
    )
    parser.add_argument("reelprofile", help="ReelProfile.json 경로")
    parser.add_argument("video", help="원본 영상 경로")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env", override=False)
    rp_path = Path(args.reelprofile)
    video = Path(args.video)
    if not rp_path.exists():
        print(f"파일 없음: {rp_path}", file=sys.stderr)
        return 1
    if not video.exists():
        print(f"영상 없음: {video}", file=sys.stderr)
        return 1

    fill(rp_path, video)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
