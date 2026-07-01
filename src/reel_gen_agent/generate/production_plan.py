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


def _lane_available(lane: str, env: dict[str, str]) -> bool:
    """VIDEO_MODEL_PRIORITY 항목의 lane에 필요한 자격이 있는지. lane 접두어로 판별한다."""
    lane = lane.lower()
    if lane.startswith("fal"):
        return bool(env.get("FAL_KEY"))
    if lane.startswith("vertex"):
        return bool(env.get("GOOGLE_CLOUD_PROJECT"))
    if lane.startswith("gemini"):
        return bool(env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY"))
    return False


def _select_video_model(env: dict[str, str]) -> str | None:
    """영상 모델을 고른다. VIDEO_MODEL_PRIORITY(lane:model, 콤마 구분)를 순회하며 lane 자격이
    있는 첫 후보를 쓴다. 없으면 레거시 폴백(VEO_MODEL / GCP·FAL 키). 다 없으면 None(ken_burns).

    이렇게 해야 .env의 우선순위(예: fal Kling 최우선)가 실제로 반영된다(예전엔 VEO_MODEL만 봤다).
    """
    prio = (env.get("VIDEO_MODEL_PRIORITY") or "").strip()
    for entry in prio.split(","):
        entry = entry.strip()
        if not entry:
            continue
        lane, sep, model = entry.partition(":")
        model = (model if sep else "").strip() or lane.strip()
        if _lane_available(lane.strip(), env):
            return model
    # 레거시 폴백(우선순위 미설정/자격 없음).
    if env.get("VEO_MODEL"):
        return env["VEO_MODEL"]
    if env.get("GOOGLE_CLOUD_PROJECT"):
        return "veo-3.1-fast-generate-001"
    if env.get("FAL_KEY"):
        return "fal-ai/kling-video/o3/standard/image-to-video"
    return None


def motion_for_panel(
    panel: StoryboardPanel, general_index: int = 0, product_index: int = 0
) -> str:
    """패널의 beat + 제품 잠금으로 컷 모션을 고른다([2026-07-01-ken-burns-motion-design.md]).

    컷마다 카메라를 다르게 움직여 컷 변화를 준다:
    - hook: 또렷한 push_in으로 시선을 잡는다.
    - 제품 강조 컷(product_lock): 제품으로 줌인한다. 제품 컷이 연속이면 강한 줌인
      (product_push_in)과 약한 줌인(zoom_in_slow)을 번갈아, 인접 컷 경계를 다르게 하되
      방향은 항상 안쪽(제품 쪽)으로 유지한다.
    - 그 외 일반 컷: 약한 줌인/줌아웃을 번갈아 인접 컷 경계를 다르게 한다.

    어색해지기 쉬운 좌우 팬과, conformance not_frozen을 건드리는 완전 정지는 쓰지 않는다.
    """
    b = (panel.beat or "").strip().lower()
    if b == "hook":
        return "push_in"
    if panel.product_lock:
        # 제품 강조: 항상 제품 쪽으로 줌인, 연속 컷은 줌 세기를 번갈아 경계를 살린다.
        return "product_push_in" if product_index % 2 == 0 else "zoom_in_slow"
    return "zoom_in_slow" if general_index % 2 == 0 else "zoom_out_slow"


def _panel_dur(panel: StoryboardPanel) -> float:
    """패널 길이(초). 없으면 최소 0.5초."""
    return max(0.5, (panel.t_end or 0.0) - (panel.t_start or 0.0))


def segment_panels(
    panels: list[StoryboardPanel], max_clip_sec: float, per_panel: bool
) -> list[list[int]]:
    """패널을 영상 모델 1회 호출 단위(세그먼트)로 묶는다([multishot-segments.md]).

    per_panel(ken_burns)이면 패널마다 세그먼트 1개다(로컬 합성이라 호출 개념이 없다).
    영상 모델이면 연속 패널을 max_clip_sec 이하로 그리디하게 묶어, ≤15초 릴이 ≤2회
    호출로 끝나게 한다. 단일 패널이 상한을 넘어도 최소 한 세그먼트로 담는다.
    """
    if per_panel:
        return [[i] for i in range(len(panels))]
    segments: list[list[int]] = []
    current: list[int] = []
    acc = 0.0
    for i, panel in enumerate(panels):
        d = _panel_dur(panel)
        if current and acc + d > max_clip_sec + 1e-6:
            segments.append(current)
            current = []
            acc = 0.0
        current.append(i)
        acc += d
    if current:
        segments.append(current)
    return segments


def _panel_motions(panels: list[StoryboardPanel]) -> list[str]:
    """패널 목록을 모션 목록으로. 일반 컷/제품 컷 교대 인덱스를 따로 센다."""
    motions: list[str] = []
    general = 0
    product = 0
    for panel in panels:
        motion = motion_for_panel(panel, general, product)
        if panel.product_lock and (panel.beat or "").strip().lower() != "hook":
            product += 1
        elif motion in ("zoom_in_slow", "zoom_out_slow"):
            general += 1
        motions.append(motion)
    return motions


def resolve_plan(profile: ReelProfile, env: dict[str, str]) -> ProductionPlan:
    fallbacks: list[str] = []
    panels = profile.storyboard.panels or []
    n = max(1, len(panels))

    video_model = _select_video_model(env)
    if video_model is None:
        video_model = "ken_burns"
        fallbacks.append("no_video_key->ken_burns")
    cap = capability_for(video_model)

    # ken_burns는 패널 수만큼 같은 렌더러를 쓰되 단일 패널이면 한 줄로 둔다.
    is_ken_burns = video_model == "ken_burns"
    if is_ken_burns:
        renderers = ["ken_burns"] * n
    else:
        renderers = ["i2v"] * n

    # 세그먼트: 영상 모델은 max_clip_sec로 묶어 ≤15초를 ≤2회 호출. ken_burns는 패널당 1개.
    segments = segment_panels(panels, cap.max_clip_sec, per_panel=is_ken_burns)

    delivery = profile.narration.delivery
    if delivery == "none":
        voice_strategy = "none"
    elif delivery == "on_camera":
        # 온카메라 발화: 영상 모델이 네이티브 음성·립싱크를 내면 integrated로 간다(별도 TTS 없음).
        # 세그먼트당 1회 호출이라 세그먼트 안에서는 음색이 일관된다. 세그먼트가 여러 개면 Veo는
        # 컷 사이 음색이 살짝 달라질 수 있고(멀티세그 일관은 fal Kling이 낫다), 기록만 남긴다.
        if cap.integrated_voice:
            voice_strategy = "integrated"
            if len(segments) > 1 and cap.lane != "fal":
                fallbacks.append("on_camera_multiseg_voice_may_drift")
        else:
            voice_strategy = "separate_tts"
            fallbacks.append("on_camera_no_integrated_voice->voiceover")
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
        segments=segments,
        bgm=profile.production_intent.bgm_pref,
        sfx=profile.production_intent.sfx_pref,
        fallbacks_applied=fallbacks,
    )
