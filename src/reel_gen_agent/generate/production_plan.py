"""ProductionIntent + capability + 가용 리소스 -> ProductionPlan.

이식 가능한 의도(ReelProfile)를 머신 환경에 맞춰 해소하고, 적용한 폴백을 남긴다.
voice 기본은 나레이션(voiceover). on_camera 멀티컷 일관은 Kling O3 Pro만 가능하므로
그 백엔드가 없으면 voiceover로 안전하게 내려간다([ADR.md] ADR-0012).
"""

from __future__ import annotations

from .capability import capability_for
from .schema import ProductionPlan, ReelProfile, StoryboardPanel

_VIDEO_KEYS = ("GOOGLE_CLOUD_PROJECT", "FAL_KEY")  # 하나라도 있으면 영상 백엔드 가능


def _has_video_backend(env: dict[str, str]) -> bool:
    return any(env.get(k) for k in _VIDEO_KEYS)


def motion_for_beat(beat: str | None, general_index: int = 0) -> str:
    """켄 번스 폴백 모션을 beat로 고른다([2026-07-01-ken-burns-motion-design.md]).

    hook은 또렷한 push_in, proof/cta는 완전 정지(static). 그 외 일반 컷은 약한 줌인/줌아웃을
    번갈아(general_index 홀짝) 인접 컷 경계를 다르게 한다. 어색한 좌우 팬은 쓰지 않는다.
    """
    b = (beat or "").strip().lower()
    if b == "hook":
        return "push_in"
    if b in ("proof", "cta"):
        return "static"
    return "zoom_in_slow" if general_index % 2 == 0 else "zoom_out_slow"


def _panel_motions(panels: list[StoryboardPanel]) -> list[str]:
    """패널 목록을 beat 기반 모션 목록으로. 일반 컷만 줌인/줌아웃 교대 인덱스를 센다."""
    motions: list[str] = []
    general = 0
    for panel in panels:
        motion = motion_for_beat(panel.beat, general)
        if motion in ("zoom_in_slow", "zoom_out_slow"):
            general += 1
        motions.append(motion)
    return motions


def resolve_plan(profile: ReelProfile, env: dict[str, str]) -> ProductionPlan:
    fallbacks: list[str] = []
    panels = profile.storyboard.panels or []
    n = max(1, len(panels))

    if _has_video_backend(env):
        video_model = env.get("VEO_MODEL", "veo-3.1-lite-generate-001")
    else:
        video_model = "ken_burns"
        fallbacks.append("no_video_key->ken_burns")
    cap = capability_for(video_model)

    # ken_burns는 패널 수만큼 같은 렌더러를 쓰되 단일 패널이면 한 줄로 둔다.
    if video_model == "ken_burns":
        renderers = ["ken_burns"] * n
    else:
        renderers = ["i2v"] * n

    delivery = profile.narration.delivery
    if delivery == "none":
        voice_strategy = "none"
    elif delivery == "on_camera":
        # on_camera 멀티컷 음성 일관은 fal 레인(Kling O3 Pro)만 가능하다.
        kling_multicut = cap.integrated_voice and (n == 1 or cap.lane == "fal")
        if kling_multicut:
            voice_strategy = "integrated"
        else:
            voice_strategy = "separate_tts"
            fallbacks.append("on_camera_multicut_needs_kling->voiceover")
    else:  # voiceover (기본)
        voice_strategy = "separate_tts"

    return ProductionPlan(
        video_model=video_model,
        capability=cap,
        voice_strategy=voice_strategy,
        multishot=cap.multishot,
        key_image_per_cut=(video_model != "ken_burns"),
        panel_renderers=renderers,
        panel_motions=_panel_motions(panels),
        bgm=profile.production_intent.bgm_pref,
        sfx=profile.production_intent.sfx_pref,
        fallbacks_applied=fallbacks,
    )
