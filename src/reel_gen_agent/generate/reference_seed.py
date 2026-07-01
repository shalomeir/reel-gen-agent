"""레퍼런스 시딩: 레퍼런스 영상을 analyze해 ReelProfile 베이스라인을 뽑는다.

레퍼런스가 있으면 plan은 최대한 레퍼런스에서 생성한다(specs/information-schema.md
"레퍼런스 시딩 범위"). 컷 리듬·팔레트·톤·자막·후크·음악 bpm과 컷 수까지 끌어와, 목적·
캐릭터·제품에 맞춰 적응시킬 베이스라인으로 쓴다. 결정론 수치는 그대로, 지각 필드는 참고.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..analysis.analyze import analyze_video
from ..analysis.profile import VideoProfile
from .schema import (
    CutRhythm,
    HookCandidate,
    InputMeta,
    MusicSpec,
    StyleDimensions,
    SubtitleSpec,
)

_ALLOWED_FPS = {24, 25, 30, 50, 60}


@dataclass
class ReferenceSeed:
    meta: InputMeta
    style: StyleDimensions
    music: MusicSpec
    hook: HookCandidate | None
    narrative_arc: list[str]
    cut_count: int
    delivery: str = "voiceover"  # 레퍼런스의 발화 방식: voiceover / on_camera / none
    seeds: dict = field(default_factory=dict)


def _delivery_from(vp: VideoProfile) -> str:
    """레퍼런스 보이스로 전달 방식을 정한다([ADR.md] ADR-0012).

    인물이 카메라 보고 직접 말하면(on_camera) 생성도 온카메라 립싱크(영상 모델 네이티브 음성)로
    재현한다. 화면 밖 나레이션이면 voiceover, 보이스가 아예 없으면 none(뮤직 베드만).
    """
    if not vp.voice.present:
        return "none"
    return "on_camera" if vp.voice.on_camera else "voiceover"


_DEFAULT_DURATION = 14.0  # 기본 제작 포맷 상한. 레퍼런스가 더 짧으면 그 길이를 반영한다.


def _meta_from(vp: VideoProfile) -> InputMeta:
    # 레퍼런스가 14초보다 짧으면 그 길이를, 길면 기본 14초로 캡한다(사용자 지시).
    dur = min(max(vp.container.duration_sec or _DEFAULT_DURATION, 1.0), _DEFAULT_DURATION)
    fps = int(round(vp.container.fps)) if vp.container.fps else 30
    if fps not in _ALLOWED_FPS:
        fps = 30
    # 해상도는 1080x1920 기본(9:16)을 유지한다. 레퍼런스가 저해상이어도 업스케일 가드레일 안.
    return InputMeta(duration_sec=round(dur, 2), fps=fps)


def _hook_from(vp: VideoProfile) -> HookCandidate | None:
    if not (vp.hook.headline or vp.hook.visual):
        return None
    w = vp.hook.window_sec or [0.0, 3.0]
    return HookCandidate(
        # 분석은 유형을 분류하지 않는다. 임시값일 뿐, plan의 후크 노드에서 LLM이 제품·목적에
        # 맞춰 유형을 다시 고른다(H1로 고정하지 않는다). 여기선 시각 컨셉의 운반체다.
        hook_type="H1",
        headline=vp.hook.headline,
        bottom_caption=vp.hook.bottom_caption,
        visual_direction=vp.hook.visual or "",
        window_sec=(float(w[0]), float(w[1] if len(w) > 1 else 3.0)),
        rationale="레퍼런스 0~3초 후크에서 시딩.",
    )


def seed_from_reference(ref_path: str, *, use_gemini: bool = True) -> ReferenceSeed:
    """레퍼런스를 analyze해 스타일/메타/음악/후크/컷수 시드를 만든다."""
    vp = analyze_video(ref_path, use_gemini=use_gemini)
    cut = vp.cut
    style = StyleDimensions(
        tone=list(vp.tone),
        pacing=cut.mode,
        cut_rhythm=CutRhythm(
            basis="beat_sync" if cut.sync == "beat_based" else "semantic_action",
            pattern=(f"{cut.count} cuts, mean {cut.mean_sec}s, {cut.mode}"),
            source="reference",
        ),
        hook=_hook_from(vp),
        subtitle=SubtitleSpec(
            style=vp.subtitle.font_style,
            position=vp.subtitle.position,
            density=vp.subtitle.density,
        ),
        palette=list(vp.visual.palette),
    )
    bpm = vp.music.bpm
    music = MusicSpec(
        mood=vp.tone[0] if vp.tone else None,
        dynamics=vp.music.dynamics,
        tempo=f"{int(bpm)} bpm" if bpm else None,
    )
    return ReferenceSeed(
        meta=_meta_from(vp),
        style=style,
        music=music,
        hook=style.hook,
        narrative_arc=list(vp.narrative_arc),
        cut_count=cut.count or 0,
        delivery=_delivery_from(vp),
        seeds={
            "cut_count": cut.count,
            "cut_mean_sec": cut.mean_sec,
            "cut_mode": cut.mode,
            "bpm": bpm,
            "reference": ref_path,
        },
    )
