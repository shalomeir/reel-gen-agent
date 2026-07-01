"""예상 비용 추정: ReelProfile + ProductionPlan + RunManifest -> CostReport.

report 노드가 회차 리포트에 넣는 모델별 예상 비용을 낸다. 생성 파이프라인은 건드리지
않고, report 시점에 이미 관측 가능한 데이터에서 실사용량을 유도해 공개 단가 근사치와
곱한다. 실제 청구가 아니라 예상치이며, 로컬 폴백(ken_burns/합성 BGM)은 $0으로 잡는다.

설계 근거: [docs/superpowers/specs/2026-07-01-report-cost-estimate-design.md],
단가·모델 선택 근거: [specs/ai-model-records.md].
"""

from __future__ import annotations

import math
import os

from .schema import CostLine, CostReport, ProductionPlan, ReelProfile, RunManifest

# 단가 기준일. 아래 PRICING은 이 날짜의 공개 단가 근사치다. 갱신은 이 파일만 고친다.
PRICING_AS_OF = "2026-07-01"

# 모델 ID -> (단위, USD 단가). 값은 공개 근사치이며 실제 청구와 다를 수 있다.
# 단위: "sec"(초), "image"(장), "1k_chars"(1k자), "clip"(클립), "call"(호출).
# 초당 영상 단가는 오디오 on/off로 갈리므로 여기 두지 않고 VIDEO_PRICING에서 따로 다룬다.
PRICING: dict[str, tuple[str, float]] = {
    # 이미지 (장당). 히어로 스틸/에셋은 Pro 모델을 4K(HERO_IMAGE_SIZE)로 뽑으므로 4K 요율
    # ($0.24/장, 2026-07 확인)을 쓴다. 코드가 히어로를 항상 4K로 생성하니 그 티어가 정본이다.
    "gemini-3.1-pro-image-preview": ("image", 0.24),
    "gemini-3.1-flash-image-preview": ("image", 0.039),
    # BGM (클립당). Lyria는 초당이 아니라 생성 1회(30초 단위 클립) 정액으로 과금한다.
    "lyria-002": ("clip", 0.04),
    # voice / SFX
    "eleven_v3": ("1k_chars", 0.18),
    "gemini-3.1-flash-tts-preview": ("1k_chars", 0.01),
    "elevenlabs-sfx": ("clip", 0.08),
    # VLM 분석 (호출당)
    "gemini-2.5-flash": ("call", 0.02),
}

# 초당 영상 단가 (audio_off, audio_on) USD. 오디오 네이티브 생성 여부로 요율이 오른다.
# 근거(2026-07 확인): fal.ai Kling O3는 티어(해상도)가 단가를 가르고 모드(i2v/ref2v)는 무관
# 하다 — Standard(720p) 0.084/0.112, Pro(1080p) 0.112/0.14. Veo 3.1은 tier별로 fast
# 0.10/0.15, quality 0.20/0.40, lite 0.03/0.05.
VIDEO_PRICING: dict[str, tuple[float, float]] = {
    "veo-fast": (0.10, 0.15),
    "veo-quality": (0.20, 0.40),
    "veo-lite": (0.03, 0.05),
    "kling-o3-standard": (0.084, 0.112),
    "kling-o3-pro": (0.112, 0.14),
}

# 기획 텍스트 LLM 토큰 단가 (USD per 1M) (input, output). 컨셉/훅/스토리보드/대사/톤 생성에 쓴다.
TEXT_TOKEN_PRICING: dict[str, tuple[float, float]] = {
    "gemini-3.1-pro-preview": (2.0, 12.0),
    "gemini-3.1-pro": (2.0, 12.0),
    "claude-opus-4-8": (5.0, 25.0),
}
# 한 회차 기획에 드는 대략적 토큰(관측 불가라 휴리스틱): intake/캐릭터/환경/음악/톤 + 훅·
# 스토리보드 핑퐁(각 최대 2회) + 대사 = 약 10회 호출. 컨텍스트가 실려 입력이 크고 출력은 작다.
LLM_EST_CALLS = 10
LLM_EST_INPUT_TOKENS = 20_000
LLM_EST_OUTPUT_TOKENS = 8_000

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


def _video_rate(model: str, audio_on: bool) -> tuple[str, float] | None:
    """초당 영상 단가를 오디오 여부로 고른다. 영상 모델이 아니면 None.

    Kling은 티어(pro/standard)로, Veo는 tier(lite/fast/quality)로 요율을 가른다. 오디오
    네이티브 생성을 켜면 audio_on 요율을, 끄면 audio_off 요율을 쓴다.
    """
    low = model.lower()
    if "kling" in low:
        off, on = VIDEO_PRICING["kling-o3-pro" if "pro" in low else "kling-o3-standard"]
    elif "veo" in low:
        if "lite" in low:
            off, on = VIDEO_PRICING["veo-lite"]
        elif "fast" in low:
            off, on = VIDEO_PRICING["veo-fast"]
        else:
            off, on = VIDEO_PRICING["veo-quality"]
    else:
        return None
    return ("sec", on if audio_on else off)


def _lookup(model: str) -> tuple[str, float] | None:
    """비영상 모델 단가를 찾는다. 정확 매칭 우선, 없으면 계열(lyria/gemini/tts) 부분 매칭.

    버전 문자열이 바뀌어도(예: lyria-002 -> lyria-3-pro-preview) 계열 단가로 잡히게 한다.
    영상(kling/veo)은 오디오 여부로 갈리므로 `_video_rate`로 넘긴다(여기선 audio_off 기준).
    """
    if model in PRICING:
        return PRICING[model]
    low = model.lower()
    if "kling" in low or "veo" in low:
        return _video_rate(model, audio_on=False)
    if "lyria" in low:
        return ("clip", 0.04)
    if "tts" in low:
        return ("1k_chars", 0.01)
    if "image" in low and "gemini" in low:
        return ("image", 0.24) if "pro" in low else ("image", 0.039)
    return None


def _video_seconds(profile: ReelProfile) -> float:
    """생성된 영상 길이(초) = 전체 패널 길이 합.

    멀티샷은 여러 패널을 한 세그먼트로 묶어 스틸 몇 장만으로 전체 구간을 생성한다.
    그래서 still_image 유무로 초를 세면 실제 생성 초를 크게 과소집계한다(예: 9패널 10.7초를
    스틸 2장만 세어 2.38초로 계산). 조립 영상 길이와 맞도록 모든 패널 길이를 합한다.
    """
    return sum(max(0.5, (p.t_end or 0.0) - (p.t_start or 0.0)) for p in profile.storyboard.panels)


def _still_count(profile: ReelProfile) -> int:
    return sum(1 for p in profile.storyboard.panels if p.still_image)


def _asset_image_count(profile: ReelProfile) -> int:
    """생성된 에셋 비블 이미지 수(캐릭터/제품/패키지/키비주얼/환경). 전부 히어로(4K)로 만든다.

    패널 스틸과 별개로 plan 단계에서 만들어지는데 예전엔 비용에서 통째로 빠졌다. 실제로 파일이
    생긴 필드만 센다(사용자 제공 에셋이 아니라 생성된 것만 근사).
    """
    ab = profile.asset_bible
    n = 0
    char = ab.character
    if char.sheet_image:
        n += 1
    if char.key_shot_image:
        n += 1
    n += sum(1 for v in char.views if v.image)
    if ab.product.hero_image:
        n += 1
    if ab.product.sheet_image:
        n += 1
    n += sum(1 for v in ab.product.views if v.image)
    if ab.key_visual:
        n += 1
    if ab.environment.needs_image and ab.environment.reference_image:
        n += 1
    return n


def _text_key_present(env: dict) -> bool:
    """기획 텍스트 LLM을 돌릴 자격이 있는지(Gemini/Vertex/Claude 중 하나)."""
    return bool(
        env.get("GEMINI_API_KEY")
        or env.get("GOOGLE_API_KEY")
        or env.get("GOOGLE_CLOUD_PROJECT")
        or env.get("ANTHROPIC_API_KEY")
    )


def _llm_line(env: dict) -> CostLine:
    """기획 텍스트 LLM(컨셉/훅/스토리보드/대사/톤)의 회차 예상 비용. 관측 불가라 휴리스틱."""
    model = env.get("GEMINI_TEXT_MODEL") or "gemini-3.1-pro-preview"
    prices = TEXT_TOKEN_PRICING.get(model)
    if prices is None:
        low = model.lower()
        prices = (5.0, 25.0) if ("claude" in low or "opus" in low) else (2.0, 12.0)
    in_price, out_price = prices
    subtotal = round(
        LLM_EST_INPUT_TOKENS / 1_000_000 * in_price + LLM_EST_OUTPUT_TOKENS / 1_000_000 * out_price,
        4,
    )
    return CostLine(
        label="기획 LLM",
        model=model,
        unit="회차",
        quantity=1,
        unit_price_usd=subtotal,
        subtotal_usd=subtotal,
        note=(
            f"추정: 약 {LLM_EST_CALLS}회 호출(입력~{LLM_EST_INPUT_TOKENS // 1000}k/"
            f"출력~{LLM_EST_OUTPUT_TOKENS // 1000}k 토큰)"
        ),
    )


def _effective_video_model(plan: ProductionPlan | None, env: dict) -> str:
    """실제로 돌아간 영상 백엔드. plan이 해소한 모델을 쓰되 REEL_VIDEO 오버라이드를 반영."""
    model = (plan.video_model if plan else None) or "ken_burns"
    if env.get("REEL_VIDEO", "").lower() == "ken_burns":
        return "ken_burns"
    return model


def _bgm_model(plan: ProductionPlan | None, env: dict) -> str:
    """실제 BGM 백엔드. plan.bgm=='gen'이고 Lyria 자격(Vertex 또는 Gemini) + REEL_BGM!=synth
    일 때만 Lyria, 아니면 합성."""
    if not plan or plan.bgm != "gen":
        return "synth" if (plan and plan.bgm != "none") else "none"
    has_lyria = (
        env.get("GOOGLE_CLOUD_PROJECT") or env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    )
    if env.get("REEL_BGM", "").lower() == "synth" or not has_lyria:
        return "synth"
    return env.get("LYRIA_MODEL") or "lyria-002"


def _tts_model(plan: ProductionPlan | None, env: dict) -> str:
    """실제 TTS 백엔드. ElevenLabs 키가 있으면 eleven_v3, 없으면 Gemini TTS 폴백."""
    if env.get("ELEVENLABS_API_KEY"):
        return env.get("ELEVENLABS_TTS_MODEL") or env.get("ELEVENLABS_MODEL") or "eleven_v3"
    return env.get("GEMINI_TTS_MODEL") or "gemini-3.1-flash-tts-preview"


def _line(
    label: str,
    model: str,
    quantity: float,
    note: str | None = None,
    audio_on: bool = False,
) -> CostLine | None:
    """모델 단가를 조회해 CostLine을 만든다. 사용량 0이면 None(라인 생략).

    영상 모델은 오디오 네이티브 생성 여부(audio_on)로 요율이 갈린다.
    """
    if quantity <= 0:
        return None
    priced = _video_rate(model, audio_on) or _lookup(model)
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
        "기획 LLM은 회차 휴리스틱 추정치(실제 토큰 사용량 관측 아님)",
        "이미지는 히어로 4K 요율. 스틸(세그먼트/컷당 1장)과 에셋(캐릭터·제품·패키지·키비주얼) 모두 집계",
        "SFX는 플랜이 켰을 때만 집계(컷 sfx 큐 기준). Kling O3는 배선되면 자동 반영",
        "재계획·재생성(run --max-iters) 반복 시 스틸/영상 비용은 회차당으로 곱해짐(1회 기준 추정)",
    ]

    # 패널 스틸 + 에셋 이미지. 에셋(캐릭터/제품/패키지/키비주얼)은 항상 히어로 4K. 패널 스틸은
    # i2v면 영상 reference라 히어로 4K, ken_burns면 로컬 팬/줌 베이스라 Flash로 뽑는다(비용 절감).
    hero_image = env.get("GEMINI_IMAGE_MODEL_HERO") or "gemini-3.1-pro-image-preview"
    flash_image = env.get("GEMINI_IMAGE_MODEL") or "gemini-3.1-flash-image-preview"
    video_model = _effective_video_model(plan, env)
    is_ken_burns = video_model == "ken_burns"
    still_model = flash_image if is_ken_burns else hero_image
    still_note = "컷당 1장(Flash, 켄번스 베이스)" if is_ken_burns else "세그먼트당 1장(히어로 4K)"
    still_count = _still_count(profile)
    line = _line("패널 스틸", still_model, still_count, note=still_note)
    if line:
        lines.append(line)
    asset_count = _asset_image_count(profile)
    line = _line(
        "에셋 이미지", hero_image, asset_count, note="캐릭터·제품·패키지·키비주얼(히어로 4K)"
    )
    if line:
        lines.append(line)

    # 영상 클립: 로컬(ken_burns)이면 라인 생략, 아니면 초당 단가.
    # 온카메라 발화(integrated)만 영상 모델이 네이티브 오디오를 내므로 audio_on 요율을 쓴다.
    # 기본 나레이션(voiceover=separate_tts)은 오디오를 끄고 생성하므로 audio_off 요율.
    video_audio_on = bool(plan and plan.voice_strategy == "integrated")
    video_seconds = _video_seconds(profile)
    n_clips = len(manifest.panel_segments)
    if video_model not in LOCAL_BACKENDS and video_seconds > 0:
        parts = [f"{n_clips}개 클립"] if n_clips else []
        parts.append("오디오 포함" if video_audio_on else "오디오 없음")
        video_note = ", ".join(parts)
        line = _line(
            "영상 클립", video_model, video_seconds, note=video_note, audio_on=video_audio_on
        )
        if line:
            lines.append(line)

    # BGM: Lyria는 클립당(30초 단위 생성 1회) 정액이라 영상 초로 곱하지 않는다. 영상 길이를
    # 30초 클립 수로 올림해 곱한다(≤30초면 1클립). 합성/무음이면 $0(라인 생략).
    bgm_model = _bgm_model(plan, env)
    if bgm_model not in LOCAL_BACKENDS and video_seconds > 0:
        bgm_clips = max(1, math.ceil(video_seconds / 30.0))
        note = f"{bgm_clips}클립(30초 단위)" if bgm_clips > 1 else None
        line = _line("BGM", bgm_model, bgm_clips, note=note)
        if line:
            lines.append(line)

    # 나레이션(TTS): voiceover(separate_tts) + 대사가 있을 때만.
    if plan and plan.voice_strategy == "separate_tts":
        chars = sum(len(ln.text) for ln in profile.narration.lines if ln.text.strip())
        line = _line("나레이션", _tts_model(plan, env), chars, note="대사 글자수 기준")
        if line:
            lines.append(line)

    # SFX(ElevenLabs): 플랜이 켰을 때만, sfx 큐가 있는 컷 수(상한 4)만큼 클립을 만든다.
    if plan and plan.sfx and env.get("ELEVENLABS_API_KEY"):
        sfx_count = min(4, sum(1 for p in profile.storyboard.panels if (p.sfx or "").strip()))
        line = _line("SFX", "elevenlabs-sfx", sfx_count, note="효과음 큐 있는 컷 수 기준")
        if line:
            lines.append(line)

    # 품질 평가(VLM): rubric이 있으면 use_vlm이 켜졌던 것 -> conformance + rubric = 2회.
    if rubric:
        vlm_model = env.get("GEMINI_ANALYSIS_MODEL") or "gemini-2.5-flash"
        line = _line("품질 평가", vlm_model, 2, note="conformance + rubric")
        if line:
            lines.append(line)

    # 기획 텍스트 LLM(컨셉/훅/스토리보드/대사/톤). 텍스트 LLM 자격이 있을 때만 회차 추정치로 넣는다.
    if _text_key_present(env):
        lines.append(_llm_line(env))

    if plan and plan.fallbacks_applied:
        caveats.append("적용된 폴백: " + ", ".join(plan.fallbacks_applied))

    # 단가 미등록 모델은 $0으로 잡히므로 과소 추정을 명시한다.
    for ln in lines:
        if ln.model not in PRICING and _lookup(ln.model) is None:
            caveats.append(f"미등록 모델(단가 미반영, $0 처리): {ln.model}")

    total = round(sum(ln.subtotal_usd for ln in lines), 4)
    return CostReport(as_of=PRICING_AS_OF, lines=lines, total_usd=total, caveats=caveats)
