"""두 VideoProfile의 유사도 비교(생성물 vs 레퍼런스).

레퍼런스가 스타일을 정한다. 이 모듈은 "생성물이 레퍼런스와 같은 결인가"를 축별로 잰다.
rubric(콘텐츠 효과성)·conformance(무결성)와 달리, 두 프로필을 한 자로 재는 유사도 게이트다.

원칙: 순수·결정론. 모델 호출 없이 이미 계산된 두 VideoProfile만 본다. 특정 레퍼런스를
하드코딩하지 않는다. 축별 점수(0~1)와, 미달 축에 대한 사람이 읽을 개선 델타를 함께 낸다.
그 델타를 plan에 피드백으로 밀어 넣어 루프를 닫는다(specs/similarity-loop.md).
"""

from __future__ import annotations

import math
import re

from pydantic import BaseModel, Field

from .profile import VideoProfile

# 축 가중치(합=1.0). 신뢰도(신호 대 노이즈)로 가중한다. rhythm/music/visual/voice/subtitle은
# 같은 영상을 다시 분석해도 안정적이라 무겁게 싣고, tone/narrative는 Gemini 자유텍스트 라벨이라
# 동일 영상조차 매 분석마다 어휘가 달라져(narrative는 특히 심함) 아주 낮게 둔다 — 측정 노이즈가
# 게이트를 좌우하지 않게 한다(사용자 우선순위: 리듬·비주얼·오디오 결).
AXIS_WEIGHTS: dict[str, float] = {
    "rhythm": 0.28,
    "voice": 0.22,
    "music": 0.15,
    "visual": 0.18,
    "subtitle": 0.09,
    "tone": 0.05,
    "narrative": 0.03,
}
OVERALL_THRESHOLD = 0.78  # 이 이상이면 "레퍼런스와 유사"로 통과
AXIS_THRESHOLD = 0.60  # 축 점수가 이 아래면 개선 델타를 낸다

# 순서형(ordinal) 축의 값 -> 위치. 인접값은 부분 점수, 반대값은 0점.
_CUT_MODE_ORDER = {"fast_montage": 0, "mixed": 1, "slow_demo": 2}
_MOTION_ORDER = {"still": 0, "gentle": 1, "dynamic": 2}
_PACE_ORDER = {"slow": 0, "medium": 1, "moderate": 1, "fast": 2}


def _ordinal_score(a: str | None, b: str | None, order: dict[str, int]) -> float | None:
    """두 순서형 라벨의 거리 점수. 값이 표에 없거나 둘 다 없으면 None(축 스킵).

    3단계 이상 척도(slow/medium/fast 등)는 인접값을 관대하게 본다(0.7). Gemini의 지각
    라벨이 같은 영상에도 인접값으로 흔들리기 때문(예: slow<->moderate)이다. 2단계 척도
    (flat/build)는 인접이 곧 양극단이라 관대 처리하지 않는다.
    """
    if not a and not b:
        return None
    ia = order.get((a or "").strip().lower())
    ib = order.get((b or "").strip().lower())
    if ia is None or ib is None:
        return None
    span = max(order.values()) - min(order.values()) or 1
    d = abs(ia - ib)
    if d == 0:
        return 1.0
    if d == 1 and span >= 2:
        return 0.7
    return max(0.0, 1.0 - d / span)


def _soft_jaccard(a: set[str], b: set[str]) -> float | None:
    """접두어 기반 soft Jaccard. 형태 변화(glow/glowy/glowing)를 같은 것으로 본다.

    한 토큰은 다른 집합에 4자 이상 공통 접두어를 가진 토큰이 있으면 매칭으로 친다. 정확
    일치보다 관대해, Gemini가 같은 뜻을 다른 단어로 라벨링해도(예: glowy/glowing) 덜 깎인다.
    양방향 매칭 비율의 조화 평균으로 대칭화한다. 둘 다 비면 None.
    """
    if not a and not b:
        return None
    if not a or not b:
        return 0.0

    def _match(tok: str, other: set[str]) -> bool:
        if tok in other:
            return True
        for o in other:
            n = min(len(tok), len(o))
            if n >= 4 and tok[:n] == o[:n]:
                return True
            if len(tok) >= 4 and len(o) >= 4 and (tok in o or o in tok):
                return True
        return False

    ma = sum(1 for t in a if _match(t, b)) / len(a)
    mb = sum(1 for t in b if _match(t, a)) / len(b)
    if ma + mb == 0:
        return 0.0
    return 2 * ma * mb / (ma + mb)


def _ratio_score(a: float | None, b: float | None) -> float | None:
    """두 양수의 비율 근접도(min/max). 로그 대칭이라 2배 차이면 0.5 근처."""
    if a is None or b is None:
        return None
    if a <= 0 and b <= 0:
        return 1.0
    if a <= 0 or b <= 0:
        return 0.0
    return min(a, b) / max(a, b)


def _abs_score(a: float | None, b: float | None, scale: float) -> float | None:
    """절대 차이 기반 근접도. |a-b|가 scale이면 0점, 0이면 1점."""
    if a is None or b is None:
        return None
    return max(0.0, 1.0 - abs(a - b) / scale)


def _bool_score(a: bool | None, b: bool | None) -> float | None:
    if a is None and b is None:
        return None
    return 1.0 if bool(a) == bool(b) else 0.0


def _tokens(*values: object) -> set[str]:
    """문자열/리스트를 소문자 토큰 집합으로. 색·톤·팔레트 겹침 계산용."""
    out: set[str] = set()
    for v in values:
        if v is None:
            continue
        items = v if isinstance(v, (list, tuple)) else [v]
        for item in items:
            # 밑줄/하이픈도 단어 경계로 쪼갠다(예: "solution_intro"->solution,intro,
            # "rose-gold"->rose,gold). 라벨 표기 차이로 의미상 같은 걸 놓치지 않게 한다.
            for tok in re.split(r"[\s,_/&-]+", str(item).strip().lower()):
                tok = tok.strip("#")
                if tok:
                    out.add(tok)
    return out


def _jaccard(a: set[str], b: set[str]) -> float | None:
    if not a and not b:
        return None
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _mean(scores: list[float | None]) -> float:
    """None(측정 불가)은 빼고 평균. 전부 None이면 비교 대상이 없다 = 차이 없음 -> 1.0."""
    vals = [s for s in scores if s is not None]
    return sum(vals) / len(vals) if vals else 1.0


class AxisScore(BaseModel):
    """유사도 한 축의 결과."""

    key: str
    weight: float
    score: float  # 0~1
    detail: str  # 레퍼런스 vs 생성물 관측값 요약
    delta: str | None = None  # 미달 축의 개선 지시(plan 피드백). 통과면 None


class SimilarityReport(BaseModel):
    """생성물 프로필 vs 레퍼런스 프로필 유사도."""

    overall: float
    passed: bool
    threshold: float = OVERALL_THRESHOLD
    axes: list[AxisScore] = Field(default_factory=list)

    def feedback(self) -> str:
        """미달 축의 델타를 한 덩어리 지시문으로. plan의 style_feedback으로 넣는다."""
        lines = [ax.delta for ax in self.axes if ax.delta]
        return "\n".join(f"- {ln}" for ln in lines)


def _rhythm_axis(ref: VideoProfile, gen: VideoProfile) -> AxisScore:
    mode = _ordinal_score(ref.cut.mode, gen.cut.mode, _CUT_MODE_ORDER)
    mean = _ratio_score(ref.cut.mean_sec, gen.cut.mean_sec)
    score = _mean([mode, mode, mean])  # mode를 두 번 실어 컷 성격을 더 무겁게 본다
    delta = None
    if score < AXIS_THRESHOLD:
        want, got = ref.cut.mean_sec, gen.cut.mean_sec
        pace_word = "faster, tighter montage cuts" if (want and got and want < got) else (
            "slower, longer, smoother holds" if (want and got and want > got) else "matched pacing"
        )
        delta = (
            f"Cut rhythm off: reference is {ref.cut.mode or '?'} at ~{ref.cut.mean_sec or '?'}s/cut, "
            f"output is {gen.cut.mode or '?'} at ~{gen.cut.mean_sec or '?'}s/cut. "
            f"Make the edit {pace_word} to match the reference's {ref.cut.mode or 'rhythm'}."
        )
    return AxisScore(
        key="rhythm", weight=AXIS_WEIGHTS["rhythm"], score=score,
        detail=f"mode {ref.cut.mode}->{gen.cut.mode}, mean {ref.cut.mean_sec}->{gen.cut.mean_sec}s",
        delta=delta,
    )


def _voice_axis(ref: VideoProfile, gen: VideoProfile) -> AxisScore:
    present = _bool_score(ref.voice.present, gen.voice.present)
    if ref.voice.present and gen.voice.present:
        oncam = _bool_score(ref.voice.on_camera, gen.voice.on_camera)
        pace = _ordinal_score(ref.voice.pace, gen.voice.pace, _PACE_ORDER)
        tone = _soft_jaccard(_tokens(ref.voice.tone), _tokens(gen.voice.tone))
        # 안정 신호(present/on_camera/pace)를 중심으로 보고, tone(결)은 soft 보너스로만 얹는다.
        # Gemini의 voice tone 라벨은 같은 영상에도 크게 흔들려(예: whispered<->enthusiastic)
        # 그대로 무겁게 실으면 노이즈가 지배한다.
        base = _mean([present, oncam, pace])
        # tone은 바닥 있는 보너스로만(최대 +20%). 노이즈로 base를 끌어내리지 않게 한다.
        score = base if tone is None else round(base * (0.8 + 0.2 * tone), 4)
    else:
        score = present if present is not None else 0.5
    delta = None
    if score < AXIS_THRESHOLD:
        delta = (
            f"Voice delivery off: reference voice is '{ref.voice.tone or '?'}' "
            f"({ref.voice.pace or '?'} pace), output is '{gen.voice.tone or '?'}' "
            f"({gen.voice.pace or '?'} pace). Match the reference delivery: same tone and pace."
        )
    return AxisScore(
        key="voice", weight=AXIS_WEIGHTS["voice"], score=score,
        detail=f"tone {ref.voice.tone!r}->{gen.voice.tone!r}, pace {ref.voice.pace}->{gen.voice.pace}",
        delta=delta,
    )


def _music_axis(ref: VideoProfile, gen: VideoProfile) -> AxisScore:
    dyn = _ordinal_score(
        ref.music.dynamics, gen.music.dynamics, {"flat": 0, "build": 1}
    )
    bpm = _ratio_score(ref.music.bpm, gen.music.bpm)
    cont = _bool_score(ref.music.continuous, gen.music.continuous)
    score = _mean([dyn, bpm, cont])
    delta = None
    if score < AXIS_THRESHOLD:
        delta = (
            f"Music character off: reference is dynamics={ref.music.dynamics or '?'}, "
            f"bpm~{ref.music.bpm or '?'}, continuous={ref.music.continuous}; "
            f"output dynamics={gen.music.dynamics or '?'}, bpm~{gen.music.bpm or '?'}. "
            "Match the reference music energy and tempo."
        )
    return AxisScore(
        key="music", weight=AXIS_WEIGHTS["music"], score=score,
        detail=f"dyn {ref.music.dynamics}->{gen.music.dynamics}, bpm {ref.music.bpm}->{gen.music.bpm}",
        delta=delta,
    )


def _visual_axis(ref: VideoProfile, gen: VideoProfile) -> AxisScore:
    motion = _ordinal_score(ref.visual.motion, gen.visual.motion, _MOTION_ORDER)
    bright = _abs_score(ref.visual.brightness, gen.visual.brightness, 128.0)
    contrast = _abs_score(ref.visual.contrast, gen.visual.contrast, 80.0)
    palette = _soft_jaccard(_tokens(ref.visual.palette), _tokens(gen.visual.palette))
    score = _mean([motion, bright, contrast, palette])
    delta = None
    if score < AXIS_THRESHOLD:
        delta = (
            f"Visual language off: reference motion={ref.visual.motion or '?'}, "
            f"brightness~{ref.visual.brightness}, palette={ref.visual.palette[:4]}; "
            f"output motion={gen.visual.motion or '?'}, brightness~{gen.visual.brightness}. "
            f"Match the reference's {ref.visual.motion or 'visual'} feel and palette."
        )
    return AxisScore(
        key="visual", weight=AXIS_WEIGHTS["visual"], score=score,
        detail=f"motion {ref.visual.motion}->{gen.visual.motion}, bright {ref.visual.brightness}->{gen.visual.brightness}",
        delta=delta,
    )


def _tone_axis(ref: VideoProfile, gen: VideoProfile) -> AxisScore:
    score = _soft_jaccard(_tokens(ref.tone), _tokens(gen.tone))
    score = 1.0 if score is None else score
    delta = None
    if score < AXIS_THRESHOLD:
        delta = (
            f"Overall tone drift: reference tone={ref.tone}, output tone={gen.tone}. "
            "Steer the concept toward the reference's tone words."
        )
    return AxisScore(
        key="tone", weight=AXIS_WEIGHTS["tone"], score=score,
        detail=f"{ref.tone} -> {gen.tone}", delta=delta,
    )


def _subtitle_axis(ref: VideoProfile, gen: VideoProfile) -> AxisScore:
    density = _ordinal_score(
        ref.subtitle.density, gen.subtitle.density,
        {"keyword": 0, "full_transcript": 1},
    )
    position = None
    if ref.subtitle.position or gen.subtitle.position:
        position = 1.0 if (ref.subtitle.position or "").lower() == (
            gen.subtitle.position or ""
        ).lower() else 0.4
    score = _mean([density, position])
    delta = None
    if score < AXIS_THRESHOLD:
        delta = (
            f"Subtitle style off: reference density={ref.subtitle.density}, "
            f"position={ref.subtitle.position}; output density={gen.subtitle.density}, "
            f"position={gen.subtitle.position}."
        )
    return AxisScore(
        key="subtitle", weight=AXIS_WEIGHTS["subtitle"], score=score,
        detail=f"density {ref.subtitle.density}->{gen.subtitle.density}", delta=delta,
    )


def _narrative_axis(ref: VideoProfile, gen: VideoProfile) -> AxisScore:
    score = _soft_jaccard(_tokens(ref.narrative_arc), _tokens(gen.narrative_arc))
    score = 1.0 if score is None else score
    delta = None
    if score < AXIS_THRESHOLD:
        delta = (
            f"Narrative arc differs: reference={ref.narrative_arc}, output={gen.narrative_arc}."
        )
    return AxisScore(
        key="narrative", weight=AXIS_WEIGHTS["narrative"], score=score,
        detail=f"{ref.narrative_arc} -> {gen.narrative_arc}", delta=delta,
    )


def compare_profiles(reference: VideoProfile, output: VideoProfile) -> SimilarityReport:
    """생성물 프로필이 레퍼런스 프로필과 얼마나 같은 결인지 잰다.

    축별 점수(0~1)를 가중 합산해 overall을 내고 threshold로 통과를 판정한다. 미달 축은
    개선 델타(plan 피드백)를 함께 담는다. 특정 레퍼런스에 특화된 상수는 쓰지 않는다.
    """
    axes = [
        _rhythm_axis(reference, output),
        _voice_axis(reference, output),
        _music_axis(reference, output),
        _visual_axis(reference, output),
        _tone_axis(reference, output),
        _subtitle_axis(reference, output),
        _narrative_axis(reference, output),
    ]
    total_w = sum(ax.weight for ax in axes) or 1.0
    overall = sum(ax.score * ax.weight for ax in axes) / total_w
    overall = round(overall, 4)
    return SimilarityReport(
        overall=overall,
        passed=overall >= OVERALL_THRESHOLD and not math.isnan(overall),
        axes=axes,
    )
