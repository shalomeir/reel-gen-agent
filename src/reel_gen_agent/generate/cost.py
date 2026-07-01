"""예상 비용 추정: ReelProfile + ProductionPlan + RunManifest -> CostReport.

report 노드가 회차 리포트에 넣는 모델별 예상 비용을 낸다. 생성 파이프라인은 건드리지
않고, report 시점에 이미 관측 가능한 데이터에서 실사용량을 유도해 공개 단가 근사치와
곱한다. 실제 청구가 아니라 예상치이며, 로컬 폴백(ken_burns/합성 BGM)은 $0으로 잡는다.

설계 근거: [docs/superpowers/specs/2026-07-01-report-cost-estimate-design.md],
단가·모델 선택 근거: [specs/ai-model-records.md].
"""

from __future__ import annotations

import os

from .schema import CostLine, CostReport, ProductionPlan, ReelProfile, RunManifest

# 단가 기준일. 아래 PRICING은 이 날짜의 공개 단가 근사치다. 갱신은 이 파일만 고친다.
PRICING_AS_OF = "2026-07-01"

# 모델 ID -> (단위, USD 단가). 값은 공개 근사치이며 실제 청구와 다를 수 있다.
# 단위: "sec"(초), "image"(장), "1k_chars"(1k자), "clip"(클립), "call"(호출).
PRICING: dict[str, tuple[str, float]] = {
    # image-to-video (초당)
    "veo-3.1-fast-generate-001": ("sec", 0.15),
    "veo-3.1-generate-001": ("sec", 0.40),
    "veo-3.1-lite-generate-001": ("sec", 0.10),
    "fal-ai/kling-video/o3/pro/reference-to-video": ("sec", 0.28),
    "fal-ai/kling-video/o3/standard/reference-to-video": ("sec", 0.14),
    "fal-ai/kling-video/o3/pro/image-to-video": ("sec", 0.28),
    "fal-ai/kling-video/o3/standard/image-to-video": ("sec", 0.14),
    # 이미지 (장당)
    "gemini-3.1-pro-image-preview": ("image", 0.12),
    "gemini-3.1-flash-image-preview": ("image", 0.039),
    # BGM (초당)
    "lyria-002": ("sec", 0.06),
    # voice / SFX
    "eleven_v3": ("1k_chars", 0.18),
    "gemini-3.1-flash-tts-preview": ("1k_chars", 0.01),
    "elevenlabs-sfx": ("clip", 0.08),
    # VLM 분석 (호출당)
    "gemini-2.5-flash": ("call", 0.02),
}

# 로컬 합성이라 과금 대상이 아닌 백엔드.
LOCAL_BACKENDS = {"ken_burns", "synth", "none", "", None}

# 단위 코드 -> 리포트 표기.
_UNIT_LABEL = {
    "sec": "초",
    "image": "장",
    "1k_chars": "1k자",
    "clip": "클립",
    "call": "호출",
}


def _lookup(model: str) -> tuple[str, float] | None:
    """모델 단가를 찾는다. 정확 매칭 우선, 없으면 kling 계열 부분 매칭 폴백."""
    if model in PRICING:
        return PRICING[model]
    low = model.lower()
    if "kling" in low:
        tier = "pro" if "pro" in low else "standard"
        mode = "reference-to-video" if "reference" in low else "image-to-video"
        key = f"fal-ai/kling-video/o3/{tier}/{mode}"
        if key in PRICING:
            return PRICING[key]
    return None


def _panel_seconds(profile: ReelProfile) -> float:
    """still_image가 있는 패널의 길이 합(초). materials의 dur 산정과 정렬."""
    total = 0.0
    for panel in profile.storyboard.panels:
        if not panel.still_image:
            continue
        total += max(0.5, (panel.t_end or 0.0) - (panel.t_start or 0.0))
    return total


def _still_count(profile: ReelProfile) -> int:
    return sum(1 for p in profile.storyboard.panels if p.still_image)


def _effective_video_model(plan: ProductionPlan | None, env: dict) -> str:
    """실제로 돌아간 영상 백엔드. plan이 해소한 모델을 쓰되 REEL_VIDEO 오버라이드를 반영."""
    model = (plan.video_model if plan else None) or "ken_burns"
    if env.get("REEL_VIDEO", "").lower() == "ken_burns":
        return "ken_burns"
    return model


def _bgm_model(plan: ProductionPlan | None, env: dict) -> str:
    """실제 BGM 백엔드. plan.bgm=='gen'이고 GCP + REEL_BGM!=synth일 때만 Lyria, 아니면 합성."""
    if not plan or plan.bgm != "gen":
        return "synth" if (plan and plan.bgm != "none") else "none"
    if env.get("REEL_BGM", "").lower() == "synth" or not env.get("GOOGLE_CLOUD_PROJECT"):
        return "synth"
    return env.get("LYRIA_MODEL") or "lyria-002"


def _tts_model(plan: ProductionPlan | None, env: dict) -> str:
    """실제 TTS 백엔드. ElevenLabs 키가 있으면 eleven_v3, 없으면 Gemini TTS 폴백."""
    if env.get("ELEVENLABS_API_KEY"):
        return env.get("ELEVENLABS_TTS_MODEL") or env.get("ELEVENLABS_MODEL") or "eleven_v3"
    return env.get("GEMINI_TTS_MODEL") or "gemini-3.1-flash-tts-preview"


def _line(label: str, model: str, quantity: float, note: str | None = None) -> CostLine | None:
    """모델 단가를 조회해 CostLine을 만든다. 사용량 0이면 None(라인 생략)."""
    if quantity <= 0:
        return None
    priced = _lookup(model)
    unit_code, unit_price = priced if priced else ("건", 0.0)
    qty = quantity / 1000.0 if unit_code == "1k_chars" else quantity
    return CostLine(
        label=label,
        model=model,
        unit=_UNIT_LABEL.get(unit_code, unit_code),
        quantity=round(qty, 4),
        unit_price_usd=unit_price,
        subtotal_usd=round(qty * unit_price, 4),
        note=note,
    )


def estimate_cost(
    profile: ReelProfile,
    plan: ProductionPlan | None,
    manifest: RunManifest,
    conformance: dict,
    rubric: dict,
    env: dict | None = None,
) -> CostReport:
    """회차 예상 비용을 낸다. report 시점 관측값에서 실사용량을 유도한다."""
    env = env if env is not None else dict(os.environ)
    lines: list[CostLine] = []
    caveats: list[str] = [
        f"단가는 공개 근사치(기준일 {PRICING_AS_OF})이며 실제 청구와 다를 수 있음",
        "ken_burns/합성 BGM 등 로컬 폴백은 $0으로 계산",
        "기획·카피 텍스트 LLM(컨셉/훅/스토리보드/대사)은 별도 planning 단계라 미포함",
        "SFX(ElevenLabs)·Kling O3는 배선되면 자동 반영, 현재 미배선분은 미집계",
        "이미지 수는 스틸 있는 패널 기준 추정(사용자 제공 스틸이 섞일 수 있음)",
    ]

    # 패널 스틸(이미지): 히어로 모델로 생성(ai-model-records §3).
    still_count = _still_count(profile)
    hero_image = env.get("GEMINI_IMAGE_MODEL_HERO") or "gemini-3.1-pro-image-preview"
    line = _line("패널 스틸", hero_image, still_count, note="스틸 있는 패널 수 기준")
    if line:
        lines.append(line)

    # 영상 클립: 로컬(ken_burns)이면 라인 생략, 아니면 초당 단가.
    video_model = _effective_video_model(plan, env)
    video_seconds = _panel_seconds(profile)
    n_clips = len(manifest.panel_segments)
    if video_model not in LOCAL_BACKENDS and video_seconds > 0:
        note = f"{n_clips}개 클립" if n_clips else None
        line = _line("영상 클립", video_model, video_seconds, note=note)
        if line:
            lines.append(line)

    # BGM: Lyria면 영상 총초 x 초당 단가, 합성/무음이면 $0(라인 생략).
    bgm_model = _bgm_model(plan, env)
    if bgm_model not in LOCAL_BACKENDS and video_seconds > 0:
        line = _line("BGM", bgm_model, video_seconds)
        if line:
            lines.append(line)

    # 나레이션(TTS): voiceover(separate_tts) + 대사가 있을 때만.
    if plan and plan.voice_strategy == "separate_tts":
        chars = sum(len(ln.text) for ln in profile.narration.lines if ln.text.strip())
        line = _line("나레이션", _tts_model(plan, env), chars, note="대사 글자수 기준")
        if line:
            lines.append(line)

    # 품질 평가(VLM): rubric이 있으면 use_vlm이 켜졌던 것 -> conformance + rubric = 2회.
    if rubric:
        vlm_model = env.get("GEMINI_ANALYSIS_MODEL") or "gemini-2.5-flash"
        line = _line("품질 평가", vlm_model, 2, note="conformance + rubric")
        if line:
            lines.append(line)

    if plan and plan.fallbacks_applied:
        caveats.append("적용된 폴백: " + ", ".join(plan.fallbacks_applied))

    # 단가 미등록 모델은 $0으로 잡히므로 과소 추정을 명시한다.
    for ln in lines:
        if ln.model not in PRICING and _lookup(ln.model) is None:
            caveats.append(f"미등록 모델(단가 미반영, $0 처리): {ln.model}")

    total = round(sum(ln.subtotal_usd for ln in lines), 4)
    return CostReport(as_of=PRICING_AS_OF, lines=lines, total_usd=total, caveats=caveats)
