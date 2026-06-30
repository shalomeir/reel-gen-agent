"""드라이버 Rubric 채점기.

숏폼 한 편을 7개 차원(D1~D7)에서 1~5점으로 판정하고, D1·D2는 곱셈 게이트로 D3~D7은
가중합 코어로 묶어 0~100점으로 환산한다. 레퍼런스와 생성물에 같은 자를 댄다. 계약과 수식의
정본은 specs/rubric.md, 배경과 근거는 docs/rubric.md에 있다.

책임 분리: Gemini 저지는 영상을 보고 1~5점과 근거만 매기고, 점수 계산(정규화, 게이트,
가중합, 통과 판정)은 이 모듈의 결정론 코드가 한다. 같은 판정 점수면 항상 같은 결과가 나온다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from . import gemini_client
from .profile import Source, VideoProfile

# --- 차원 정의 (단일 출처) -----------------------------------------------------
# (code, key, 이름, 비중, 역할). 비중 합은 1.0. 가중치는 상수가 아니라 이 표에서 읽는다.
# 표를 바꾸면 수식이 그대로 따라온다(가중치 하드코딩 금지).
DIMENSIONS: list[tuple[str, str, str, float, str]] = [
    ("D1", "hook_strength", "Hook 강도(첫 1~3초)", 0.20, "gate"),
    ("D2", "watch_completion", "시청 완결 설계", 0.18, "gate"),
    ("D3", "content_value", "콘텐츠 가치", 0.15, "additive"),
    ("D4", "brand_integration", "브랜드 통합 자연스러움", 0.14, "additive"),
    ("D5", "call_to_action", "행동 유발 설계", 0.14, "additive"),
    ("D6", "platform_native", "플랫폼 네이티브성", 0.09, "additive"),
    ("D7", "trust_authenticity", "신뢰·진정성", 0.10, "additive"),
]

GATE_CODES = [code for code, _, _, _, role in DIMENSIONS if role == "gate"]
ADDITIVE_CODES = [code for code, _, _, _, role in DIMENSIONS if role == "additive"]


# --- 게이트 설정 ----------------------------------------------------------------


class RubricGateConfig(BaseModel):
    """통과 판정 임계값. 코드에 박지 않고 주입한다."""

    min_gate_score: int = 3  # D1, D2 각각의 최소 통과 점수
    min_total: float = 40.0  # 전체 통과에 필요한 gated_score 하한


# --- 결과 스키마 (생성 게이트가 소비하는 경계) ---------------------------------


class DimensionScore(BaseModel):
    """한 차원의 채점 결과."""

    code: str  # D1..D7
    key: str
    name: str
    weight: float
    role: str  # gate / additive
    score: int  # 1~5
    normalized: float  # 0~1, (score-1)/4
    rationale: str | None = None  # 한국어 근거


class RubricResult(BaseModel):
    """영상 한 편의 Rubric 채점 결과."""

    dimensions: list[DimensionScore] = Field(default_factory=list)
    gate_coefficient: float = 0.0  # G = nrm(D1) * nrm(D2)
    additive_core: float = 0.0  # A = Σ w_norm * nrm(Di), i in D3..D7
    gated_score: float = 0.0  # G * A * 100 (정본)
    flat_score: float = 0.0  # Σ wi * nrm(Di) * 100 (보조, 전체 7개)
    gate_passed: bool = False
    passed: bool = False
    summary: str | None = None
    expected_effect: str | None = None  # 이 영상으로 기대되는 바이럴/효과 서술
    source: Source = Field(default_factory=Source)
    scored: bool = False  # 저지가 실제로 채점했는지(키 없거나 실패면 False)


# --- Gemini 저지 출력 (1~5점 + 근거만) -----------------------------------------


class DimensionJudgment(BaseModel):
    """저지가 차원 하나에 매기는 판정. 점수와 근거만, 계산은 안 함."""

    code: str  # D1..D7
    score: int  # 1~5
    rationale: str  # 한국어 근거


class RubricJudgment(BaseModel):
    """저지의 전체 판정. 7개 차원 + 한 줄 총평 + 기대 효과 서술."""

    dimensions: list[DimensionJudgment] = Field(default_factory=list)
    summary: str | None = None
    expected_effect: str | None = None  # 기대 바이럴/효과(한국어 2~3문장)


# --- 저지 프롬프트 --------------------------------------------------------------

_RUBRIC_PROMPT = """\
You are a strict short-form video judge for a vertical product-ad harness.
Score the video on 7 dimensions, each an integer 1 (failure) to 5 (excellent).
Use these anchors:
- D1 hook_strength (first 1-3s): does it give an instant reason to stop scrolling?
  1 = plain intro, slow open. 5 = first cut delivers shock/curiosity/empathy instantly.
- D2 watch_completion: is there rhythm and curiosity that holds to the end?
  1 = saggy middle, predictable end. 5 = payoff placed at the end, tight loop/pacing.
- D3 content_value: is there clear info, entertainment, or empathy?
  1 = only repeats ad copy. 5 = save-worthy tip or strong empathy.
- D4 brand_integration: does the product blend in, or scream "ad"?
  1 = product appears out of nowhere. 5 = product enters naturally as the solution.
- D5 call_to_action: is there a CTA / share / save motivation?
  1 = no or weak CTA. 5 = clear action prompt plus a share trigger.
- D6 platform_native: does it use trend sound/format/captions natively for the platform?
  1 = feels recycled from another platform. 5 = uses current trending format/sound.
- D7 trust_authenticity: is it believable without exaggeration?
  1 = overclaiming, opaque sponsorship. 5 = names skin type, admits limits, transparent.

Return one entry per dimension with its `code` (D1..D7), integer `score`, and a concise
Korean `rationale` (한국어로 한두 문장). Also give a one-line Korean `summary`, and an
`expected_effect`: 2-3 Korean sentences describing the viral potential and likely effect of
this video (who would stop and watch, save/share triggers, expected reach for this niche).
Do not compute any weighted total; only score each dimension.
"""

PROMPT_VIDEO = "Judge this vertical short video.\n" + _RUBRIC_PROMPT
PROMPT_FRAMES = (
    f"These are {gemini_client.FALLBACK_FRAMES} keyframes (no audio) sampled in order "
    "from a vertical short video.\n"
    + _RUBRIC_PROMPT
    + "\nAudio is unavailable here: judge D6/sound conservatively from the visuals only."
)


# --- 수식 (결정론) --------------------------------------------------------------


def normalize(score: int) -> float:
    """1~5점을 0~1로. 1점 -> 0.0(실패), 3점 -> 0.5, 5점 -> 1.0(탁월)."""
    clamped = max(1, min(5, int(score)))
    return (clamped - 1) / 4


def _weight_of(code: str) -> float:
    for c, _, _, weight, _ in DIMENSIONS:
        if c == code:
            return weight
    raise KeyError(code)


def compute_result(
    scores: dict[str, int],
    rationales: dict[str, str] | None = None,
    summary: str | None = None,
    expected_effect: str | None = None,
    source: Source | None = None,
    config: RubricGateConfig | None = None,
) -> RubricResult:
    """차원별 1~5 점수로 RubricResult를 계산한다(결정론).

    scores는 D1..D7 전부를 담아야 한다. 빠진 차원은 1점(실패)으로 본다.
    """
    config = config or RubricGateConfig()
    rationales = rationales or {}

    dimensions: list[DimensionScore] = []
    norm: dict[str, float] = {}
    for code, key, name, weight, role in DIMENSIONS:
        raw = int(scores.get(code, 1))
        raw = max(1, min(5, raw))
        n = normalize(raw)
        norm[code] = n
        dimensions.append(
            DimensionScore(
                code=code,
                key=key,
                name=name,
                weight=weight,
                role=role,
                score=raw,
                normalized=round(n, 4),
                rationale=rationales.get(code),
            )
        )

    # 게이트 계수 G = nrm(D1) * nrm(D2)
    gate_coefficient = 1.0
    for code in GATE_CODES:
        gate_coefficient *= norm[code]

    # 가산 코어 A = Σ (w_norm * nrm), 그룹 내 가중치 합으로 정규화
    additive_weight_sum = sum(_weight_of(code) for code in ADDITIVE_CODES)
    additive_core = 0.0
    if additive_weight_sum > 0:
        for code in ADDITIVE_CODES:
            additive_core += (_weight_of(code) / additive_weight_sum) * norm[code]

    gated_score = gate_coefficient * additive_core * 100

    # 보조: 7개 전체 단순 가중합 (비중 합 1.0 가정)
    flat_score = sum(_weight_of(code) * norm[code] for code, *_ in DIMENSIONS) * 100

    gate_passed = all(scores.get(code, 1) >= config.min_gate_score for code in GATE_CODES)
    passed = gate_passed and gated_score >= config.min_total

    return RubricResult(
        dimensions=dimensions,
        gate_coefficient=round(gate_coefficient, 4),
        additive_core=round(additive_core, 4),
        gated_score=round(gated_score, 2),
        flat_score=round(flat_score, 2),
        gate_passed=gate_passed,
        passed=passed,
        summary=summary,
        expected_effect=expected_effect,
        source=source or Source(),
        scored=True,
    )


# --- 저지 호출 + 채점 -----------------------------------------------------------


def judge(
    path: str,
    duration_sec: float | None,
    api_key: str | None = None,
    model: str | None = None,
) -> RubricJudgment | None:
    """영상을 Gemini 저지에 넣어 차원별 1~5 판정을 받는다. 실패하면 None."""
    return gemini_client.run_multimodal(
        path,
        duration_sec,
        schema=RubricJudgment,
        video_prompt=PROMPT_VIDEO,
        frames_prompt=PROMPT_FRAMES,
        api_key=api_key,
        model=model,
        log_prefix="rubric",
    )


def evaluate_video(
    path: str,
    profile: VideoProfile | None = None,
    config: RubricGateConfig | None = None,
    use_gemini: bool = True,
    judge_fn=judge,
) -> RubricResult:
    """영상 한 편을 Rubric으로 채점한다.

    profile은 출처/길이 컨텍스트로 쓴다(없으면 analyze_video로 만든다). 저지가 채점하지
    못하면(키 없음/실패) scored=False인 빈 결과를 반환해 게이트를 건너뛰게 한다.
    judge_fn은 테스트에서 주입할 수 있다.
    """
    if profile is None:
        from .analyze import analyze_video

        profile = analyze_video(path, use_gemini=use_gemini)

    source = profile.source if profile.source.path or profile.source.url else Source(path=path)

    if not use_gemini:
        return RubricResult(source=source, scored=False, summary="채점 안 함(--no-gemini)")

    judgment = judge_fn(path, profile.container.duration_sec)
    if judgment is None or not judgment.dimensions:
        return RubricResult(source=source, scored=False, summary="저지 결과 없음(키/호출 실패)")

    scores = {j.code: j.score for j in judgment.dimensions}
    rationales = {j.code: j.rationale for j in judgment.dimensions}
    result = compute_result(
        scores,
        rationales=rationales,
        summary=judgment.summary,
        expected_effect=judgment.expected_effect,
        source=source,
        config=config,
    )
    return result
