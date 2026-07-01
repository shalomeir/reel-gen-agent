import pytest
from PIL import Image, ImageDraw

from reel_gen_agent.analysis.frame_sampler import mean_adjacent_diff, sample_frames
from reel_gen_agent.analysis.media_probe import probe_container
from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend

# conformance.ConformanceConfig.freeze_min_diff 기본값. 켄 번스 모션이 이를 넘어야
# media.not_frozen 체크를 통과한다.
FREEZE_MIN_DIFF = 2.0


def _still(tmp_path):
    p = tmp_path / "still.png"
    Image.new("RGB", (1080, 1920), (200, 120, 160)).save(p)
    return str(p)


def _textured_still(tmp_path):
    """공간 디테일이 있는 스틸. 켄 번스 줌이 프레임 차이를 만들려면 무늬가 있어야 한다."""
    img = Image.new("RGB", (1080, 1920), (40, 60, 110))
    d = ImageDraw.Draw(img)
    for i in range(0, 1080, 80):
        d.rectangle([i, 0, i + 40, 1920], fill=(220, 180, 120))
    for j in range(0, 1920, 120):
        d.rectangle([0, j, 1080, j + 30], fill=(120, 200, 160))
    p = tmp_path / "textured.png"
    img.save(p)
    return str(p)


def test_ken_burns_makes_clip_of_requested_duration(tmp_path):
    out = tmp_path / "clip.mp4"
    KenBurnsBackend().render_panel(_still(tmp_path), 2.0, 1080, 1920, 30, str(out))
    meta = probe_container(str(out))
    assert out.exists()
    assert meta.duration_sec is not None
    assert abs(meta.duration_sec - 2.0) < 0.3
    # probe_container는 해상도를 "WxH" 문자열로 돌려준다.
    assert meta.resolution == "1080x1920"


@pytest.mark.parametrize("motion", ["zoom_in_slow", "zoom_out_slow", "push_in"])
def test_ken_burns_zoom_motions_exceed_freeze_threshold(tmp_path, motion):
    """줌 모션은 not_frozen 임계값을 넘겨 정지영상으로 오판되지 않아야 한다."""
    out = tmp_path / f"clip_{motion}.mp4"
    KenBurnsBackend().render_panel(
        _textured_still(tmp_path), 3.0, 540, 960, 30, str(out), motion=motion
    )
    samples = sample_frames(str(out), 12)
    assert mean_adjacent_diff(samples) > FREEZE_MIN_DIFF


def test_ken_burns_static_is_frozen(tmp_path):
    """static 모션은 완전 정지라 인접 프레임 차이가 임계값 아래여야 한다."""
    out = tmp_path / "clip_static.mp4"
    KenBurnsBackend().render_panel(
        _textured_still(tmp_path), 3.0, 540, 960, 30, str(out), motion="static"
    )
    samples = sample_frames(str(out), 12)
    assert mean_adjacent_diff(samples) < FREEZE_MIN_DIFF
