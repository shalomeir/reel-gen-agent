"""Conformance 게이트의 결정론 체크 테스트.

VLM 지각 판정은 외부 호출이라 목으로 막거나 주입한다. 미디어/템플릿/머지/스키마/3상태
로직만 실제 단언으로 덮는다. 계약은 specs/conformance-gate.md.
"""

from pathlib import Path

import pytest

from reel_gen_agent.analysis.loudness import Loudness
from reel_gen_agent.analysis.profile import Container
from reel_gen_agent.generate.conformance import (
    ConformanceConfig,
    PerceptualJudgment,
    _check_merge,
    _check_nodegraph,
    _check_perceptual_vlm,
    _check_template,
    _Facts,
    _texts_match,
    verify_conformance,
)
from reel_gen_agent.generate.schema import (
    GenerationInput,
    NodeRun,
    ProductSpec,
    RunManifest,
    Storyboard,
    StoryboardPanel,
)

ROOT = Path(__file__).resolve().parents[1]


def _facts(container=None, audio=True, loud=True, samples=0):
    """체크 입력용 합성 측정 묶음."""
    loudness = Loudness(lufs=-13.0, peak_dbfs=-2.0, measured=loud)
    return _Facts(
        file_ok=True,
        container=container,
        probe_error=None,
        samples=[],  # 미디어 프레임 체크는 별도 단언하지 않는다.
        audio_present=audio,
        loudness=loudness,
    )


def _status(checks, code):
    return next(c.status for c in checks if c.code == code)


# --- 템플릿 적합성 -------------------------------------------------------------


def test_template_duration_and_aspect_match():
    container = Container(aspect_ratio="9:16", fps=30.0, duration_sec=18.0, resolution="1080x1920")
    gen_input = GenerationInput(product=ProductSpec(name="x"))  # 기본 18s, 9:16, 30fps
    checks = _check_template(_facts(container), gen_input, ConformanceConfig())
    assert _status(checks, "template.duration_match") == "pass"
    assert _status(checks, "template.aspect_match") == "pass"
    assert _status(checks, "template.fps_match") == "pass"


def test_template_duration_mismatch_fails():
    container = Container(aspect_ratio="9:16", fps=30.0, duration_sec=40.0, resolution="1080x1920")
    gen_input = GenerationInput(product=ProductSpec(name="x"))  # 기대 18s
    checks = _check_template(_facts(container), gen_input, ConformanceConfig())
    assert _status(checks, "template.duration_match") == "fail"


def test_template_music_present_skips_when_unspecified():
    container = Container(aspect_ratio="9:16", fps=30.0, duration_sec=15.0, resolution="1080x1920")
    gen_input = GenerationInput(product=ProductSpec(name="x"))  # music 미지정
    checks = _check_template(_facts(container, audio=True), gen_input, ConformanceConfig())
    assert _status(checks, "template.music_present") == "skip"


# --- 머지 무결성 ---------------------------------------------------------------


def _panels(spans):
    return [StoryboardPanel(index=i, t_start=s, t_end=e) for i, (s, e) in enumerate(spans)]


def test_merge_timeline_contiguous_pass_and_fail():
    board_ok = Storyboard(panels=_panels([(0, 3), (3, 6), (6, 9)]))
    manifest = RunManifest(panel_segments=["a", "b", "c"])
    checks = _check_merge(manifest, board_ok, ConformanceConfig())
    assert _status(checks, "merge.timeline_contiguous") == "pass"

    board_gap = Storyboard(panels=_panels([(0, 3), (4, 6)]))  # 3~4 갭
    checks = _check_merge(RunManifest(panel_segments=["a", "b"]), board_gap, ConformanceConfig())
    assert _status(checks, "merge.timeline_contiguous") == "fail"


def test_merge_segment_count_mismatch_fails():
    board = Storyboard(panels=_panels([(0, 3), (3, 6)]))  # 패널 2개
    manifest = RunManifest(panel_segments=["a", "b", "c"])  # 세그먼트 3개
    checks = _check_merge(manifest, board, ConformanceConfig())
    assert _status(checks, "merge.segment_count") == "fail"


# --- 노드그래프/스키마 ---------------------------------------------------------


def test_nodegraph_error_node_and_missing_artifact_fail(tmp_path):
    present = tmp_path / "a.png"
    present.write_bytes(b"x")
    manifest = RunManifest(
        nodes=[
            NodeRun(name="storyboard", status="done", artifacts=[str(present)]),
            NodeRun(name="video", status="error", artifacts=[str(tmp_path / "missing.mp4")]),
        ]
    )
    checks = _check_nodegraph(manifest, None)
    assert _status(checks, "nodegraph.all_nodes_done") == "fail"
    assert _status(checks, "nodegraph.artifacts_exist") == "fail"


def test_nodegraph_schema_valid_pass_and_fail(tmp_path):
    good = tmp_path / "input.json"
    good.write_text(GenerationInput(product=ProductSpec(name="x")).model_dump_json(), "utf-8")
    bad = tmp_path / "board.json"
    bad.write_text('{"panels": "not-a-list"}', "utf-8")

    manifest = RunManifest(input_path=str(good), storyboard_path=str(bad))
    checks = _check_nodegraph(manifest, None)
    assert _status(checks, "nodegraph.input_schema_valid") == "pass"
    assert _status(checks, "nodegraph.storyboard_schema_valid") == "fail"


# --- 지각 결함(VLM) ------------------------------------------------------------


def test_perceptual_clean_passes_intrinsic():
    judgment = PerceptualJudgment(subtitle_present=True, subtitle_texts=["반짝 글로우 ✨"])
    checks = _check_perceptual_vlm(judgment, None, None)
    assert _status(checks, "perceptual.cut_transition_clean") == "pass"
    assert _status(checks, "perceptual.subtitle_in_safe_zone") == "pass"
    assert _status(checks, "perceptual.subtitle_legible") == "pass"


def test_perceptual_defects_fail():
    judgment = PerceptualJudgment(
        subtitle_present=True,
        subtitle_texts=["x"],
        subtitle_awkward=True,
        subtitle_effect_broken=True,
        has_broken_frames=True,
    )
    checks = _check_perceptual_vlm(judgment, None, None)
    assert _status(checks, "perceptual.cut_transition_clean") == "fail"
    assert _status(checks, "perceptual.subtitle_not_awkward") == "fail"
    assert _status(checks, "perceptual.subtitle_legible") == "fail"


def test_perceptual_none_skips_all():
    checks = _check_perceptual_vlm(None, None, None)
    assert all(c.status == "skip" for c in checks)


def test_texts_match():
    assert _texts_match(["Glow routine"], ["glow routine ✨"]) is True
    assert _texts_match(["완전 다른 텍스트"], ["unrelated caption"]) is False
    assert _texts_match([], ["anything"]) is True  # 기대 없음 -> 통과


# --- 오케스트레이션 (실제 영상, VLM 목) ----------------------------------------


def _sample_video():
    folder = ROOT / "reference_video"
    if not folder.exists():
        return None
    videos = sorted(folder.glob("*.mp4"))
    return videos[0] if videos else None


SAMPLE = _sample_video()


@pytest.mark.skipif(SAMPLE is None, reason="reference_video/ 아래 mp4가 없으면 건너뛴다")
def test_verify_reference_passes_with_mocked_clean_vlm():
    """레퍼런스를 기대 스펙 없이 검증하면 intrinsic만 돌고 PASS여야 한다(VLM은 clean으로 목)."""
    report = verify_conformance(
        str(SAMPLE),
        judge_fn=lambda *a, **k: PerceptualJudgment(subtitle_present=True, subtitle_texts=["ok"]),
    )
    # 템플릿/머지/노드 체크는 전부 skip이어야 한다(기대 스펙 없음).
    assert all(
        c.status == "skip"
        for c in report.checks
        if c.category in {"template", "merge", "nodegraph", "cross"}
    )
    # 미디어 핵심 체크는 통과.
    assert _status(report.checks, "media.file_valid") == "pass"
    assert _status(report.checks, "media.aspect_ratio") == "pass"
    assert report.passed is True


def test_passed_is_false_when_any_check_fails(tmp_path):
    """존재하지 않는 파일은 미디어 체크가 fail이라 passed=False."""
    report = verify_conformance(str(tmp_path / "nope.mp4"), use_vlm=False)
    assert report.passed is False
    assert report.counts["fail"] >= 1
