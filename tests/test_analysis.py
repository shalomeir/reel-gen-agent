"""Deterministic-layer smoke tests.

The Gemini perceptual layer is an external call and is excluded here. These tests
cover the local layer and the catalog writer. Tests that need a real video run
against the first mp4 found under reference_video/, and skip if none exists.
"""

from pathlib import Path

import pytest

from reel_gen_agent.analysis.cut_detector import detect_cuts
from reel_gen_agent.analysis.list_writer import to_list_entry
from reel_gen_agent.analysis.media_probe import probe_container
from reel_gen_agent.analysis.profile import VideoProfile
from reel_gen_agent.analysis.visual_features import extract_visual_features

ROOT = Path(__file__).resolve().parents[1]


def _sample_video():
    """첫 번째로 발견되는 레퍼런스 mp4. 없으면 None."""
    folder = ROOT / "reference_video"
    if not folder.exists():
        return None
    videos = sorted(folder.glob("*.mp4"))
    return videos[0] if videos else None


SAMPLE = _sample_video()
requires_sample = pytest.mark.skipif(
    SAMPLE is None, reason="reference_video/ 아래 mp4가 없으면 건너뛴다"
)


@requires_sample
def test_probe_container_reads_vertical_short():
    """세로 숏폼이면 종횡비/ fps / 길이가 채워져야 한다."""
    container = probe_container(str(SAMPLE))
    assert container.aspect_ratio
    assert container.fps and container.fps > 0
    assert container.duration_sec and container.duration_sec > 0


@requires_sample
def test_detect_cuts_returns_distribution():
    """컷 수와 평균 컷 길이가 산출돼야 한다."""
    cut = detect_cuts(str(SAMPLE))
    assert cut.count >= 1
    if cut.count > 1:
        assert cut.mean_sec is not None and cut.mean_sec > 0
        assert cut.mode in {"fast_montage", "slow_demo", "mixed", "single_take"}


@requires_sample
def test_visual_features_return_palette_and_brightness():
    """색 팔레트(hex)와 밝기 / 대비 수치가 나와야 한다."""
    palette, brightness, contrast = extract_visual_features(str(SAMPLE))
    assert palette and all(p.startswith("#") for p in palette)
    assert 0 <= brightness <= 255
    assert contrast >= 0


def test_list_writer_renders_entry_without_gemini():
    """비정형 필드가 비어도 카탈로그 항목 마크다운이 형식대로 나와야 한다."""
    profile = VideoProfile()
    profile.container.resolution = "1080x1920"
    profile.container.aspect_ratio = "9:16"
    profile.container.fps = 24.0
    profile.container.duration_sec = 15.0
    profile.cut.count = 7
    profile.cut.mean_sec = 2.2
    profile.cut.mode = "slow_demo"
    profile.source.url = "https://example.com/x"

    entry = to_list_entry(profile, "Sample Video", index=3)
    assert entry.startswith("### 3. Sample Video")
    assert "9:16" in entry
    assert "7컷" in entry
    assert "넣은 의도" in entry
