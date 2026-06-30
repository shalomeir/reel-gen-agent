"""ProductionIntent + capability + 가용 리소스 -> ProductionPlan.

이식 가능한 의도(ReelProfile)를 머신 환경에 맞춰 해소하고, 적용한 폴백을 남긴다.
voice 기본은 나레이션(voiceover). on_camera 멀티컷 일관은 Kling O3 Pro만 가능하므로
그 백엔드가 없으면 voiceover로 안전하게 내려간다([ADR.md] ADR-0012).
"""

from __future__ import annotations

from .capability import capability_for
from .schema import ProductionPlan, ReelProfile

_VIDEO_KEYS = ("GOOGLE_CLOUD_PROJECT", "FAL_KEY")  # 하나라도 있으면 영상 백엔드 가능


def _has_video_backend(env: dict[str, str]) -> bool:
    return any(env.get(k) for k in _VIDEO_KEYS)


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
        bgm=profile.production_intent.bgm_pref,
        sfx=profile.production_intent.sfx_pref,
        fallbacks_applied=fallbacks,
    )
