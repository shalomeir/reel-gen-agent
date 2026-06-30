"""Conformance 게이트: 결과물 무결성·적합성 검증.

생성된 영상이 의도한 템플릿대로 기술적으로 온전히 만들어졌고 노드 산출물이 빠짐없이 머지
됐는지를 하드 pass/fail로 판정한다. 계약과 체크 카탈로그의 정본은 specs/conformance-gate.md.

3상태(pass/fail/skip): 평가에 필요한 기대 스펙(템플릿/스토리보드/매니페스트)이 없으면 skip.
전체 passed = fail 0개(skip은 통과). 레퍼런스는 intrinsic 체크만 돌고 나머지는 skip이라,
잘 만든 레퍼런스는 모두 PASS다. 깨진 파일이나 디코드 실패는 예외로 던지지 않고 해당 체크
fail로 환원해 게이트 자체가 죽지 않게 한다.

지각 결함(자막 위치·효과, 컷 전환)은 Gemini 멀티모달로 binary 판정하고, 볼륨과 깨진 프레임
은 결정론으로 본다. 점수가 아니라 명백한 결함만 잡는다(정성 채점은 rubric의 몫).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from ..analysis import gemini_client
from ..analysis.frame_sampler import (
    FrameSample,
    black_frame_ratio,
    interior_black_flicker,
    mean_adjacent_diff,
    sample_frames,
)
from ..analysis.loudness import Loudness, measure_loudness
from ..analysis.media_probe import (
    has_audio_stream,
    probe_container,
    stream_durations,
)
from ..analysis.profile import Container, Source
from .schema import GenerationInput, RunManifest, Storyboard

PASS = "pass"
FAIL = "fail"
SKIP = "skip"


# --- 설정 ----------------------------------------------------------------------


class ConformanceConfig(BaseModel):
    """체크 임계값. 코드에 박지 않고 주입한다."""

    expected_aspect_ratio: str = "9:16"
    # 최소 가로 폭. 실측 레퍼런스(576-wide)를 통과시키되 명백한 저해상도는 거른다.
    min_width: int = 480
    duration_tolerance_sec: float = 0.75
    duration_tolerance_ratio: float = 0.10
    fps_tolerance: float = 1.0
    platform_max_sec: dict[str, float] = Field(
        default_factory=lambda: {"tiktok": 600.0, "reels": 90.0, "shorts": 60.0}
    )
    black_luma_max: float = 12.0
    max_black_ratio: float = 0.9
    freeze_min_diff: float = 2.0
    silence_floor_dbfs: float = -60.0
    # 라우드니스 범위는 마스터링 타깃이 아니라 극단(near-silent/over-loud)만 거르는 새너티
    # 폭이다. 실측 레퍼런스가 기준선이라 가장 조용한 레퍼런스(약 -26 LUFS)도 통과시킨다.
    # 생성물에는 config 주입으로 더 타이트한 타깃을 걸 수 있다.
    lufs_min: float = -30.0
    lufs_max: float = -5.0
    # 샘플 피크 기준 클리핑 판정. 실제 풀스케일(0 dBFS) 도달만 잡는다.
    true_peak_max_dbtp: float = 0.0
    cut_count_tolerance: int = 2
    sample_frames: int = 16
    av_sync_tolerance_sec: float = 0.5
    duration_sum_tolerance_sec: float = 0.75
    timeline_eps_sec: float = 0.05


# --- 결과 스키마 (생성 게이트가 소비하는 경계) ---------------------------------


class ConformanceCheck(BaseModel):
    """체크 하나의 결과."""

    code: str  # 범주.이름
    category: str  # media / template / nodegraph / merge / cross / perceptual
    intrinsic: bool  # True면 레퍼런스에서도 평가
    status: str  # pass / fail / skip
    expected: str | None = None
    actual: str | None = None
    detail: str | None = None  # 한국어


class ConformanceReport(BaseModel):
    """영상 한 편의 conformance 검증 결과."""

    checks: list[ConformanceCheck] = Field(default_factory=list)
    passed: bool = False
    counts: dict[str, int] = Field(default_factory=dict)
    source: Source = Field(default_factory=Source)


# --- 지각 판정(VLM) 스키마 -----------------------------------------------------


class PerceptualJudgment(BaseModel):
    """Gemini가 보고하는 지각 결함. 기본값은 모두 '결함 없음'으로 둔다.

    누락 필드가 거짓 fail을 내지 않게 한다. binary 판정만, 점수는 매기지 않는다.
    """

    subtitle_texts: list[str] = Field(default_factory=list)
    subtitle_present: bool = False
    subtitle_in_safe_zone: bool = True
    subtitle_awkward: bool = False  # True = 결함(피사체 가림/어색)
    subtitle_legible: bool = True
    subtitle_effect_broken: bool = False  # True = 결함(이모지 두부/효과 깨짐)
    cut_transition_clean: bool = True
    has_broken_frames: bool = False  # True = 결함(컷에 깨진 블랙/플리커)
    product_present: bool = False
    product_fit_purpose: bool = True  # False = 결함(제품이 목적에 안 맞게 표현/거의 안 보임)
    model_present: bool = False
    model_appeal_fit: bool = True  # False = 결함(등장인물이 목적 전달에 부적절)
    detail: str | None = None


_PERCEPTUAL_PROMPT = """\
You are a strict but fair defect detector for a vertical short-form video.
Report ONLY clear, obvious defects. If something looks fine or you are unsure, mark it as
no defect (the optimistic default). Do not nitpick stylistic choices.

Fill the schema:
- subtitle_texts: transcribe the on-screen caption text lines you can read (empty if none).
- subtitle_present: true if there are on-screen captions.
- subtitle_in_safe_zone: false ONLY if captions are cut off at the frame edge or sit under
  the platform UI zone (very top bar / very bottom caption bar / right action column).
- subtitle_awkward: true ONLY if captions clearly cover the subject's face or key product.
- subtitle_legible: false ONLY if captions are hard to read (no outline/contrast, tiny).
- subtitle_effect_broken: true ONLY if emoji render as tofu/black boxes or glyphs are broken.
- cut_transition_clean: false ONLY if cuts are visibly jarring or broken.
- has_broken_frames: true ONLY if there are corrupt/black/flicker frames mid-clip.
- product_present: true if a product is featured in the video.
- product_fit_purpose: false ONLY if the product is barely shown, distorted, or clearly
  not represented in a way that serves the video's apparent purpose.
- model_present: true if a person/model appears on camera.
- model_appeal_fit: false ONLY if the person clearly does not fit or lacks the appeal needed
  to carry this kind of short-form product video.
- detail: one short Korean sentence summarizing any defects (or that it looks clean).
"""

PROMPT_VIDEO = "Inspect this vertical short video for defects.\n" + _PERCEPTUAL_PROMPT
PROMPT_FRAMES = (
    f"These are {gemini_client.FALLBACK_FRAMES} keyframes (no audio) sampled in order from a "
    "vertical short video.\n"
    + _PERCEPTUAL_PROMPT
    + "\nAudio is unavailable here: judge only what the frames show."
)


def judge_perceptual(
    path: str,
    duration_sec: float | None,
    api_key: str | None = None,
    model: str | None = None,
) -> PerceptualJudgment | None:
    """영상을 Gemini에 넣어 지각 결함을 binary로 판정받는다. 실패하면 None(체크는 skip)."""
    return gemini_client.run_multimodal(
        path,
        duration_sec,
        schema=PerceptualJudgment,
        video_prompt=PROMPT_VIDEO,
        frames_prompt=PROMPT_FRAMES,
        api_key=api_key,
        model=model,
        log_prefix="conformance",
    )


# --- 측정 묶음 (한 번만 수집) --------------------------------------------------


@dataclass
class _Facts:
    file_ok: bool
    container: Container | None
    probe_error: str | None
    samples: list[FrameSample]
    audio_present: bool
    loudness: Loudness


def _gather(path: str, config: ConformanceConfig) -> _Facts:
    """체크 여러 곳이 공유하는 측정을 한 번에 수집한다."""
    p = Path(path)
    file_ok = p.exists() and p.is_file() and p.stat().st_size > 0

    container: Container | None = None
    probe_error: str | None = None
    samples: list[FrameSample] = []
    audio_present = False
    loud = Loudness(lufs=-120.0, peak_dbfs=-120.0, measured=False)

    if file_ok:
        try:
            container = probe_container(path)
        except Exception as exc:  # 손상/비영상 파일
            probe_error = str(exc)
        samples = sample_frames(path, config.sample_frames)
        audio_present = has_audio_stream(path)
        loud = measure_loudness(path)

    return _Facts(file_ok, container, probe_error, samples, audio_present, loud)


def _chk(code, category, intrinsic, status, expected=None, actual=None, detail=None):
    return ConformanceCheck(
        code=code,
        category=category,
        intrinsic=intrinsic,
        status=status,
        expected=None if expected is None else str(expected),
        actual=None if actual is None else str(actual),
        detail=detail,
    )


def _width_of(resolution: str | None) -> int | None:
    """'1080x1920' -> 1080. 파싱 실패 시 None."""
    if not resolution or "x" not in resolution:
        return None
    try:
        return int(resolution.split("x")[0])
    except ValueError:
        return None


# --- A. 미디어 무결성 (intrinsic) ----------------------------------------------


def _check_media(facts: _Facts, config: ConformanceConfig) -> list[ConformanceCheck]:
    c = facts.container
    checks = [
        _chk(
            "media.file_valid",
            "media",
            True,
            PASS if (facts.file_ok and c is not None) else FAIL,
            detail=facts.probe_error or ("파일 유효, ffprobe 파싱됨" if c else "파일 없음/0바이트"),
        ),
        _chk(
            "media.container_complete",
            "media",
            True,
            PASS if (c and c.duration_sec is not None) else FAIL,
            detail="컨테이너 길이 정보 존재(잘림 없음)"
            if (c and c.duration_sec is not None)
            else "길이 정보 없음(잘렸을 수 있음)",
        ),
        _chk(
            "media.video_decodable",
            "media",
            True,
            PASS if facts.samples else FAIL,
            actual=f"{len(facts.samples)} frames",
            detail="프레임 디코드됨" if facts.samples else "프레임 디코드 실패",
        ),
        _chk(
            "media.audio_present",
            "media",
            True,
            PASS if facts.audio_present else FAIL,
            detail="오디오 스트림 존재" if facts.audio_present else "오디오 스트림 없음",
        ),
        _chk(
            "media.aspect_ratio",
            "media",
            True,
            PASS if (c and c.aspect_ratio == config.expected_aspect_ratio) else FAIL,
            expected=config.expected_aspect_ratio,
            actual=c.aspect_ratio if c else None,
        ),
        _chk(
            "media.duration_positive",
            "media",
            True,
            PASS if (c and c.duration_sec and c.duration_sec > 0) else FAIL,
            actual=c.duration_sec if c else None,
        ),
    ]

    width = _width_of(c.resolution if c else None)
    checks.append(
        _chk(
            "media.resolution_min",
            "media",
            True,
            PASS if (width is not None and width >= config.min_width) else FAIL,
            expected=f">= {config.min_width}px wide",
            actual=c.resolution if c else None,
        )
    )

    if facts.samples:
        black_ratio = black_frame_ratio(facts.samples, config.black_luma_max)
        checks.append(
            _chk(
                "media.not_black",
                "media",
                True,
                PASS if black_ratio < config.max_black_ratio else FAIL,
                actual=f"black ratio {black_ratio:.2f}",
                detail="대부분 검은 화면"
                if black_ratio >= config.max_black_ratio
                else "정상 밝기 프레임 존재",
            )
        )
        adj = mean_adjacent_diff(facts.samples)
        checks.append(
            _chk(
                "media.not_frozen",
                "media",
                True,
                PASS if adj >= config.freeze_min_diff else FAIL,
                actual=f"adjacent diff {adj:.2f}",
                detail="정지영상에 가까움" if adj < config.freeze_min_diff else "프레임 변화 있음",
            )
        )

    if facts.audio_present:
        not_silent = (
            facts.loudness.measured and facts.loudness.peak_dbfs > config.silence_floor_dbfs
        )
        checks.append(
            _chk(
                "media.audio_not_silent",
                "media",
                True,
                PASS if not_silent else FAIL,
                actual=f"peak {facts.loudness.peak_dbfs} dBFS",
                detail="전체 무음에 가까움" if not not_silent else "오디오 신호 존재",
            )
        )

    return checks


# --- E(결정론 부분). 볼륨 + 깨진 프레임 (intrinsic) ----------------------------


def _check_volume_and_frames(facts: _Facts, config: ConformanceConfig) -> list[ConformanceCheck]:
    checks: list[ConformanceCheck] = []

    if facts.loudness.measured:
        in_range = config.lufs_min <= facts.loudness.lufs <= config.lufs_max
        checks.append(
            _chk(
                "perceptual.volume_loudness",
                "perceptual",
                True,
                PASS if in_range else FAIL,
                expected=f"{config.lufs_min} ~ {config.lufs_max} LUFS",
                actual=f"{facts.loudness.lufs} LUFS",
            )
        )
        checks.append(
            _chk(
                "perceptual.volume_no_clipping",
                "perceptual",
                True,
                PASS if facts.loudness.peak_dbfs <= config.true_peak_max_dbtp else FAIL,
                expected=f"<= {config.true_peak_max_dbtp} dBTP",
                actual=f"{facts.loudness.peak_dbfs} dBFS",
            )
        )
    else:
        for code in ("perceptual.volume_loudness", "perceptual.volume_no_clipping"):
            checks.append(_chk(code, "perceptual", True, SKIP, detail="오디오 측정 불가"))

    if facts.samples:
        flicker = interior_black_flicker(facts.samples, config.black_luma_max)
        checks.append(
            _chk(
                "perceptual.cut_no_broken_frames",
                "perceptual",
                True,
                FAIL if flicker else PASS,
                detail="중간에 깨진 블랙/플리커 프레임 의심" if flicker else "깨진 프레임 없음",
            )
        )

    return checks


# --- B. 템플릿 적합성 (template-derived) ---------------------------------------


def _check_template(
    facts: _Facts, gen_input: GenerationInput, config: ConformanceConfig
) -> list[ConformanceCheck]:
    c = facts.container
    meta = gen_input.meta
    checks: list[ConformanceCheck] = []

    if c and c.duration_sec is not None:
        tol = max(
            config.duration_tolerance_sec, config.duration_tolerance_ratio * meta.duration_sec
        )
        ok = abs(c.duration_sec - meta.duration_sec) <= tol
        checks.append(
            _chk(
                "template.duration_match",
                "template",
                False,
                PASS if ok else FAIL,
                expected=f"{meta.duration_sec}s ± {tol:.2f}",
                actual=f"{c.duration_sec}s",
            )
        )
    else:
        checks.append(
            _chk("template.duration_match", "template", False, SKIP, detail="길이 측정 불가")
        )

    checks.append(
        _chk(
            "template.aspect_match",
            "template",
            False,
            PASS if (c and c.aspect_ratio == meta.aspect_ratio) else FAIL,
            expected=meta.aspect_ratio,
            actual=c.aspect_ratio if c else None,
        )
    )

    if c and c.fps is not None:
        checks.append(
            _chk(
                "template.fps_match",
                "template",
                False,
                PASS if abs(c.fps - meta.fps) <= config.fps_tolerance else FAIL,
                expected=f"{meta.fps} ± {config.fps_tolerance}",
                actual=c.fps,
            )
        )
    else:
        checks.append(_chk("template.fps_match", "template", False, SKIP, detail="fps 측정 불가"))

    limit = config.platform_max_sec.get(meta.platform)
    if c and c.duration_sec is not None and limit is not None:
        checks.append(
            _chk(
                "template.duration_within_platform",
                "template",
                False,
                PASS if c.duration_sec <= limit else FAIL,
                expected=f"<= {limit}s ({meta.platform})",
                actual=f"{c.duration_sec}s",
            )
        )
    else:
        checks.append(
            _chk(
                "template.duration_within_platform",
                "template",
                False,
                SKIP,
                detail="플랫폼 상한 미정 또는 길이 측정 불가",
            )
        )

    # voice_mode / music_present: 음성 검출은 추후, 음악 베드는 오디오 존재로 본다.
    if gen_input.voice.enabled:
        checks.append(
            _chk("template.voice_mode", "template", False, SKIP, detail="음성 검출은 추후 구현")
        )
    else:
        checks.append(
            _chk(
                "template.voice_mode",
                "template",
                False,
                PASS if facts.audio_present else FAIL,
                detail="music bed(오디오) 존재" if facts.audio_present else "오디오 없음",
            )
        )

    music_expected = bool(gen_input.music.mood or gen_input.music.dynamics)
    if music_expected:
        checks.append(
            _chk(
                "template.music_present",
                "template",
                False,
                PASS if facts.audio_present else FAIL,
                detail="오디오 트랙 존재" if facts.audio_present else "오디오 없음",
            )
        )
    else:
        checks.append(_chk("template.music_present", "template", False, SKIP, detail="음악 미지정"))

    if gen_input.watermark:
        checks.append(
            _chk(
                "template.watermark_present",
                "template",
                False,
                SKIP,
                detail="워터마크 자동 검출 미구현(매니페스트 적용 기록으로 추후 검증)",
            )
        )

    return checks


# --- E(VLM 부분). 자막 위치·효과, 컷 전환 ---------------------------------------


def _check_perceptual_vlm(
    judgment: PerceptualJudgment | None,
    gen_input: GenerationInput | None,
    storyboard: Storyboard | None,
) -> list[ConformanceCheck]:
    # VLM 결과가 없으면(키 없음/끔/실패) 모두 skip. skip은 통과라 게이트를 막지 않는다.
    if judgment is None:
        codes = [
            "perceptual.cut_transition_clean",
            "perceptual.subtitle_in_safe_zone",
            "perceptual.subtitle_not_awkward",
            "perceptual.subtitle_legible",
            "perceptual.product_fit_purpose",
            "perceptual.model_appeal_fit",
            "perceptual.subtitle_text_match",
            "perceptual.transition_as_specified",
        ]
        return [
            _chk(
                code,
                "perceptual",
                code != "perceptual.subtitle_text_match",
                SKIP,
                detail="VLM 미실행",
            )
            for code in codes
        ]

    checks: list[ConformanceCheck] = [
        _chk(
            "perceptual.cut_transition_clean",
            "perceptual",
            True,
            PASS if (judgment.cut_transition_clean and not judgment.has_broken_frames) else FAIL,
            detail=judgment.detail,
        )
    ]

    has_subs = judgment.subtitle_present or bool(judgment.subtitle_texts)
    if has_subs:
        checks += [
            _chk(
                "perceptual.subtitle_in_safe_zone",
                "perceptual",
                True,
                PASS if judgment.subtitle_in_safe_zone else FAIL,
                detail="자막이 화면 밖/UI 영역 침범"
                if not judgment.subtitle_in_safe_zone
                else None,
            ),
            _chk(
                "perceptual.subtitle_not_awkward",
                "perceptual",
                True,
                PASS if not judgment.subtitle_awkward else FAIL,
                detail="자막이 피사체/제품을 가림" if judgment.subtitle_awkward else None,
            ),
            _chk(
                "perceptual.subtitle_legible",
                "perceptual",
                True,
                PASS
                if (judgment.subtitle_legible and not judgment.subtitle_effect_broken)
                else FAIL,
                detail="가독성 낮음/효과 깨짐"
                if (not judgment.subtitle_legible or judgment.subtitle_effect_broken)
                else None,
            ),
        ]
    else:
        for code in (
            "perceptual.subtitle_in_safe_zone",
            "perceptual.subtitle_not_awkward",
            "perceptual.subtitle_legible",
        ):
            checks.append(_chk(code, "perceptual", True, SKIP, detail="자막 없음"))

    # 제품 표현 적절성 / 등장인물 매력 적합성 (intrinsic). 없으면 skip.
    if judgment.product_present:
        checks.append(
            _chk(
                "perceptual.product_fit_purpose",
                "perceptual",
                True,
                PASS if judgment.product_fit_purpose else FAIL,
                detail="제품이 목적에 맞게 표현되지 않음/거의 안 보임"
                if not judgment.product_fit_purpose
                else "제품이 목적에 맞게 표현됨",
            )
        )
    else:
        checks.append(
            _chk("perceptual.product_fit_purpose", "perceptual", True, SKIP, detail="제품 미등장")
        )

    if judgment.model_present:
        checks.append(
            _chk(
                "perceptual.model_appeal_fit",
                "perceptual",
                True,
                PASS if judgment.model_appeal_fit else FAIL,
                detail="등장인물이 목적 전달에 부적절"
                if not judgment.model_appeal_fit
                else "등장인물이 목적 전달에 적절",
            )
        )
    else:
        checks.append(
            _chk("perceptual.model_appeal_fit", "perceptual", True, SKIP, detail="등장인물 미등장")
        )

    # 자막 텍스트 일치 (template-derived): 스토리보드의 subtitle_text와 대조.
    expected_texts = (
        [p.subtitle_text for p in storyboard.panels if p.subtitle_text] if storyboard else []
    )
    if storyboard is not None and expected_texts:
        ok = _texts_match(expected_texts, judgment.subtitle_texts)
        checks.append(
            _chk(
                "perceptual.subtitle_text_match",
                "perceptual",
                False,
                PASS if ok else FAIL,
                expected=" | ".join(expected_texts[:3]),
                actual=" | ".join(judgment.subtitle_texts[:3]),
            )
        )
    else:
        checks.append(
            _chk(
                "perceptual.subtitle_text_match",
                "perceptual",
                False,
                SKIP,
                detail="기대 자막 없음(레퍼런스/무자막)",
            )
        )

    # 지정 전환 적용 여부: 스토리보드에 전환 타입 필드가 아직 없어 계약상 skip.
    checks.append(
        _chk(
            "perceptual.transition_as_specified",
            "perceptual",
            False,
            SKIP,
            detail="스토리보드 전환 타입 필드 추후",
        )
    )

    return checks


def _texts_match(expected: list[str], read: list[str]) -> bool:
    """기대 자막의 절반 이상이 읽힌 자막과 매칭되면 True(느슨한 대조)."""

    def norm(s: str) -> str:
        return "".join(s.lower().split())

    exp = [norm(e) for e in expected if e]
    rd = [norm(r) for r in read if r]
    if not exp:
        return True
    if not rd:
        return False
    matched = 0
    for e in exp:
        best = max((difflib.SequenceMatcher(None, e, r).ratio() for r in rd), default=0.0)
        contained = any(e in r or r in e for r in rd)
        if best >= 0.6 or contained:
            matched += 1
    return matched >= max(1, len(exp) // 2)


# --- C. 노드그래프·머지 무결성 (template-derived) -------------------------------


def _check_nodegraph(
    manifest: RunManifest, storyboard: Storyboard | None
) -> list[ConformanceCheck]:
    checks: list[ConformanceCheck] = []

    errored = [n.name for n in manifest.nodes if n.status == "error"]
    checks.append(
        _chk(
            "nodegraph.all_nodes_done",
            "nodegraph",
            False,
            FAIL if errored else PASS,
            actual=f"error nodes: {errored}" if errored else "no error",
        )
    )

    missing = [a for n in manifest.nodes for a in n.artifacts if not _file_nonempty(a)]
    checks.append(
        _chk(
            "nodegraph.artifacts_exist",
            "nodegraph",
            False,
            FAIL if missing else PASS,
            actual=f"missing: {missing[:3]}" if missing else "all present",
        )
    )

    checks.append(
        _schema_check("nodegraph.input_schema_valid", manifest.input_path, GenerationInput)
    )
    checks.append(
        _schema_check("nodegraph.storyboard_schema_valid", manifest.storyboard_path, Storyboard)
    )

    if storyboard is not None and storyboard.panels:
        no_still = [p.index for p in storyboard.panels if not _file_nonempty(p.still_image)]
        checks.append(
            _chk(
                "nodegraph.panel_stills_exist",
                "nodegraph",
                False,
                FAIL if no_still else PASS,
                actual=f"panels w/o still: {no_still}" if no_still else "all panels have stills",
            )
        )
        locked = [p for p in storyboard.panels if p.subject_lock or p.product_lock]
        bad_lock = [p.index for p in locked if not _file_nonempty(p.still_image)]
        checks.append(
            _chk(
                "nodegraph.asset_lock_referenced",
                "nodegraph",
                False,
                FAIL if bad_lock else PASS,
                detail=f"잠금 패널 still 누락: {bad_lock}" if bad_lock else "잠금 패널 에셋 반영",
            )
        )
    else:
        checks.append(
            _chk("nodegraph.panel_stills_exist", "nodegraph", False, SKIP, detail="스토리보드 없음")
        )
        checks.append(
            _chk(
                "nodegraph.asset_lock_referenced",
                "nodegraph",
                False,
                SKIP,
                detail="스토리보드 없음",
            )
        )

    if manifest.panel_segments:
        missing_clips = [s for s in manifest.panel_segments if not _file_nonempty(s)]
        checks.append(
            _chk(
                "nodegraph.panel_clips_exist",
                "nodegraph",
                False,
                FAIL if missing_clips else PASS,
                actual=f"missing clips: {missing_clips[:3]}"
                if missing_clips
                else "all clips present",
            )
        )
    else:
        checks.append(
            _chk("nodegraph.panel_clips_exist", "nodegraph", False, SKIP, detail="세그먼트 미기록")
        )

    return checks


def _check_merge(
    manifest: RunManifest, storyboard: Storyboard | None, config: ConformanceConfig
) -> list[ConformanceCheck]:
    checks: list[ConformanceCheck] = []
    panels = storyboard.panels if storyboard else []

    if panels and manifest.panel_segments:
        ok = len(manifest.panel_segments) == len(panels)
        checks.append(
            _chk(
                "merge.segment_count",
                "merge",
                False,
                PASS if ok else FAIL,
                expected=f"{len(panels)} panels",
                actual=f"{len(manifest.panel_segments)} segments",
            )
        )
    else:
        checks.append(
            _chk("merge.segment_count", "merge", False, SKIP, detail="패널/세그먼트 미기록")
        )

    if panels:
        ordered = sorted(panels, key=lambda p: p.index)
        gap = False
        for p in ordered:
            if p.t_end <= p.t_start:
                gap = True
        for a, b in zip(ordered, ordered[1:], strict=False):
            if abs(b.t_start - a.t_end) > config.timeline_eps_sec:
                gap = True
        checks.append(
            _chk(
                "merge.timeline_contiguous",
                "merge",
                False,
                FAIL if gap else PASS,
                detail="패널 타임라인 갭/오버랩 또는 t_end<=t_start" if gap else "타임라인 연속",
            )
        )
    else:
        checks.append(
            _chk("merge.timeline_contiguous", "merge", False, SKIP, detail="스토리보드 없음")
        )

    final = manifest.final_video
    final_dur = _safe_duration(final)
    if panels and final_dur is not None:
        panel_sum = sum(p.t_end - p.t_start for p in panels)
        ok = abs(panel_sum - final_dur) <= config.duration_sum_tolerance_sec
        checks.append(
            _chk(
                "merge.duration_sum",
                "merge",
                False,
                PASS if ok else FAIL,
                expected=f"{panel_sum:.2f}s ± {config.duration_sum_tolerance_sec}",
                actual=f"{final_dur:.2f}s",
            )
        )
    else:
        checks.append(
            _chk("merge.duration_sum", "merge", False, SKIP, detail="final 영상/스토리보드 없음")
        )

    if final and _file_nonempty(final):
        vdur, adur = stream_durations(final)
        if vdur is not None and adur is not None:
            ok = abs(vdur - adur) <= config.av_sync_tolerance_sec
            checks.append(
                _chk(
                    "merge.av_sync",
                    "merge",
                    False,
                    PASS if ok else FAIL,
                    expected=f"|v-a| <= {config.av_sync_tolerance_sec}s",
                    actual=f"v={vdur:.2f}s a={adur:.2f}s",
                )
            )
        else:
            checks.append(_chk("merge.av_sync", "merge", False, SKIP, detail="스트림 길이 미상"))
    else:
        checks.append(_chk("merge.av_sync", "merge", False, SKIP, detail="final 영상 없음"))

    return checks


# --- D. 레이어 교차 일관성 (template-derived) ----------------------------------


def _check_cross(
    facts: _Facts, storyboard: Storyboard, config: ConformanceConfig, path: str
) -> list[ConformanceCheck]:
    # final 영상을 재분석해 컷 수가 스토리보드 패널 수와 근사한지 본다.
    panel_count = len(storyboard.panels)
    if panel_count == 0:
        return [_chk("cross.cut_count_match", "cross", False, SKIP, detail="패널 없음")]
    try:
        from ..analysis.cut_detector import detect_cuts

        cut = detect_cuts(path)
        ok = abs(cut.count - panel_count) <= config.cut_count_tolerance
        return [
            _chk(
                "cross.cut_count_match",
                "cross",
                False,
                PASS if ok else FAIL,
                expected=f"{panel_count} ± {config.cut_count_tolerance}",
                actual=f"{cut.count} cuts",
            )
        ]
    except Exception as exc:
        return [_chk("cross.cut_count_match", "cross", False, SKIP, detail=f"컷 분석 실패: {exc}")]


# --- 헬퍼 ----------------------------------------------------------------------


def _file_nonempty(path: str | None) -> bool:
    if not path:
        return False
    p = Path(path)
    return p.exists() and p.is_file() and p.stat().st_size > 0


def _safe_duration(path: str | None) -> float | None:
    if not _file_nonempty(path):
        return None
    try:
        return probe_container(path).duration_sec  # type: ignore[arg-type]
    except Exception:
        return None


def _schema_check(code: str, json_path: str | None, model: type[BaseModel]) -> ConformanceCheck:
    """JSON 파일이 주어진 pydantic 스키마를 통과하는지 검사한다."""
    if not json_path:
        return _chk(code, "nodegraph", False, SKIP, detail="경로 미기록")
    if not _file_nonempty(json_path):
        return _chk(code, "nodegraph", False, FAIL, detail="파일 없음")
    try:
        model.model_validate_json(Path(json_path).read_text(encoding="utf-8"))
        return _chk(code, "nodegraph", False, PASS)
    except (ValidationError, ValueError) as exc:
        return _chk(code, "nodegraph", False, FAIL, detail=f"스키마 위반: {exc}")


# --- 오케스트레이터 ------------------------------------------------------------


def verify_conformance(
    path: str,
    gen_input: GenerationInput | None = None,
    storyboard: Storyboard | None = None,
    manifest: RunManifest | None = None,
    config: ConformanceConfig | None = None,
    use_vlm: bool = True,
    judge_fn=judge_perceptual,
) -> ConformanceReport:
    """영상 한 편을 conformance로 검증한다.

    기대 스펙(gen_input/storyboard/manifest)이 없으면 그 범주는 skip된다. 레퍼런스는
    아무것도 넘기지 않으면 intrinsic 체크만 돌고 PASS여야 한다. judge_fn은 테스트 주입용.
    """
    config = config or ConformanceConfig()
    facts = _gather(path, config)
    duration = facts.container.duration_sec if facts.container else None

    checks: list[ConformanceCheck] = []
    checks += _check_media(facts, config)
    checks += _check_volume_and_frames(facts, config)

    if gen_input is not None:
        checks += _check_template(facts, gen_input, config)

    judgment = judge_fn(path, duration) if use_vlm else None
    checks += _check_perceptual_vlm(judgment, gen_input, storyboard)

    if manifest is not None:
        checks += _check_nodegraph(manifest, storyboard)
        checks += _check_merge(manifest, storyboard, config)

    if storyboard is not None:
        checks += _check_cross(facts, storyboard, config, path)

    counts = {
        PASS: sum(1 for c in checks if c.status == PASS),
        FAIL: sum(1 for c in checks if c.status == FAIL),
        SKIP: sum(1 for c in checks if c.status == SKIP),
    }
    source = Source(path=path)
    return ConformanceReport(checks=checks, passed=counts[FAIL] == 0, counts=counts, source=source)
