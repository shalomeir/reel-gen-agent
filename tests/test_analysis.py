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
from reel_gen_agent.analysis.reference import add_reference
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


def _stub_profile() -> VideoProfile:
    """add_reference 흐름 테스트용 최소 프로필."""
    profile = VideoProfile()
    profile.container.resolution = "1080x1920"
    profile.container.aspect_ratio = "9:16"
    profile.cut.count = 5
    profile.cut.mode = "slow_demo"
    return profile


def test_add_reference_flow_downloads_analyzes_and_catalogs(tmp_path):
    """URL 하나로 다운로드 -> 분석 -> 프로필 저장 -> 카탈로그가 한 번에 일어나야 한다.

    다운로더와 분석기를 주입해 네트워크/ffmpeg 없이 오케스트레이션만 검증한다.
    """
    # 다운로더가 받았다고 가정할 가짜 영상 파일을 만들어 둔다.
    video = tmp_path / "reference_video" / "Sample_Clip [Demo-abc123].mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"fake")

    captured = {}

    def fake_downloader(url, project_root, cookies_from_browser=None):
        captured["url"] = url
        captured["cookies"] = cookies_from_browser
        return video

    def fake_analyzer(path, url=None, use_gemini=True):
        captured["analyzed_path"] = path
        captured["use_gemini"] = use_gemini
        return _stub_profile()

    result = add_reference(
        "https://example.com/p/abc123/",
        project_root=tmp_path,
        cookies_from_browser="chrome",
        use_gemini=False,
        downloader=fake_downloader,
        analyzer=fake_analyzer,
    )

    # 다운로더/분석기가 올바른 인자로 호출됐는가.
    assert captured["url"] == "https://example.com/p/abc123/"
    assert captured["cookies"] == "chrome"
    assert captured["analyzed_path"] == str(video)
    assert captured["use_gemini"] is False

    # 프로필 JSON이 profiles/ 아래에 영상 stem 이름으로 저장됐는가.
    assert result.profile_path == tmp_path / "profiles" / f"{video.stem}.json"
    assert result.profile_path.exists()

    # 카탈로그가 머리말과 함께 만들어지고 첫 항목(#1)이 들어갔는가.
    assert result.catalog_index == 1
    catalog_text = result.catalog_path.read_text("utf-8")
    assert "## 목록" in catalog_text
    # 제목은 파일명에서 출처 꼬리표([Demo-abc123])를 떼고 남긴다.
    assert "### 1. Sample_Clip" in catalog_text
    assert "[Demo-abc123]" not in catalog_text


def test_add_reference_appends_with_incrementing_index(tmp_path):
    """이미 항목이 있는 카탈로그에는 다음 번호로 덧붙어야 한다."""
    video = tmp_path / "reference_video" / "Second [Demo-xyz].mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"fake")

    catalog = tmp_path / "reference_video" / "list.md"
    catalog.write_text("## 목록\n\n### 1. First\n- 출처: x\n", encoding="utf-8")

    result = add_reference(
        "https://example.com/2",
        project_root=tmp_path,
        downloader=lambda url, root, cookies_from_browser=None: video,
        analyzer=lambda path, url=None, use_gemini=True: _stub_profile(),
    )

    assert result.catalog_index == 2
    text = catalog.read_text("utf-8")
    assert "### 1. First" in text
    assert "### 2. Second" in text


def test_add_reference_can_skip_catalog(tmp_path):
    """--no-catalog 경로: 프로필은 저장하되 list.md는 건드리지 않는다."""
    video = tmp_path / "reference_video" / "NoCat [Demo-1].mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"fake")

    result = add_reference(
        "https://example.com/3",
        project_root=tmp_path,
        write_catalog=False,
        downloader=lambda url, root, cookies_from_browser=None: video,
        analyzer=lambda path, url=None, use_gemini=True: _stub_profile(),
    )

    assert result.catalog_path is None
    assert result.catalog_index is None
    assert result.profile_path.exists()
    assert not (tmp_path / "reference_video" / "list.md").exists()
