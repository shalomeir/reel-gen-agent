from PIL import Image

from reel_gen_agent.analysis.media_probe import probe_container
from reel_gen_agent.generate.assemble import (
    _concat_with_seams,
    _group_by_sizes,
    _native_ambience_gain,
    _shift_spans_for_seams,
    assemble,
)
from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend
from reel_gen_agent.generate.schema import InputMeta, Materials


def _clip(tmp_path, name, dur):
    still = tmp_path / f"{name}.png"
    Image.new("RGB", (540, 960), (180, 140, 200)).save(still)
    out = tmp_path / f"{name}.mp4"
    KenBurnsBackend().render_panel(str(still), dur, 540, 960, 30, str(out))
    return str(out)


def test_assemble_concats_to_expected_duration(tmp_path):
    mats = Materials(shot_clips=[_clip(tmp_path, "a", 1.0), _clip(tmp_path, "b", 1.0)])
    out = tmp_path / "final.mp4"
    assemble(mats, InputMeta(width=540, height=960), str(out))
    meta = probe_container(str(out))
    assert out.exists()
    assert meta.duration_sec is not None
    assert abs(meta.duration_sec - 2.0) < 0.4
    assert meta.resolution == "540x960"


def test_group_by_sizes_splits_and_rejects_mismatch():
    assert _group_by_sizes(["a", "b", "c"], [1, 2]) == [["a"], ["b", "c"]]
    # 0 크기 세그먼트는 빈 그룹을 만들지 않는다.
    assert _group_by_sizes(["a", "b"], [0, 2]) == [["a", "b"]]
    # 합이 안 맞으면 None(하드컷 폴백).
    assert _group_by_sizes(["a", "b"], [1]) is None
    assert _group_by_sizes(["a", "b"], []) is None


def test_shift_spans_for_seams_pulls_by_seams_before():
    # 이음매가 t=1.0 하나, transition=0.3. 이음매 전 span은 그대로, 후 span은 0.3 당겨진다.
    spans = [[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]]
    out = _shift_spans_for_seams(spans, seam_times=[1.0], transition=0.3)
    assert out[0] == [0.0, 1.0]  # 이음매 전
    assert out[1] == [0.7, 1.7]  # 이음매(1.0<=1.0)에서 한 번 당겨짐
    assert out[2] == [1.7, 2.7]


def test_shift_spans_two_seams_accumulate():
    spans = [[0.5, 1.0], [3.0, 3.5]]
    out = _shift_spans_for_seams(spans, seam_times=[1.0, 2.0], transition=0.5)
    assert out[0] == [0.5, 1.0]  # 이음매 앞
    assert out[1] == [2.0, 2.5]  # 이음매 2개 뒤 -> 1.0 당김


def test_native_ambience_gain_rules():
    # 온카메라 발화면 네이티브가 곧 목소리 -> 또렷하게 1.0(BGM은 덕킹).
    assert _native_ambience_gain(True, True, has_bgm=True, has_voice=False) == 1.0
    assert _native_ambience_gain(True, True, has_bgm=False, has_voice=False) == 1.0
    # 앰비언스 + BGM + 나레이션 없음(music_bed) -> 끈다(0.0).
    assert _native_ambience_gain(True, False, has_bgm=True, has_voice=False) == 0.0
    # 앰비언스 + BGM + 나레이션 있음 -> 아주 낮게(0.12).
    assert _native_ambience_gain(True, False, has_bgm=True, has_voice=True) == 0.12
    # BGM 없으면 앰비언스 그대로(None=기본 0.30).
    assert _native_ambience_gain(True, False, has_bgm=False, has_voice=False) is None
    # 네이티브 자체가 없으면 None.
    assert _native_ambience_gain(False, False, has_bgm=True, has_voice=False) is None


def test_concat_with_seams_crossfades_only_at_boundaries(tmp_path):
    # 세그먼트 [a,b](각 1초) + [c](1초). 세그먼트 안 a,b는 하드컷, 경계(b->c)만 xfade 0.3.
    # 총 길이 3초 - 이음매 1개*0.3 = 2.7초.
    clips = [
        _clip(tmp_path, "a", 1.0),
        _clip(tmp_path, "b", 1.0),
        _clip(tmp_path, "c", 1.0),
    ]
    out = tmp_path / "seamed.mp4"
    seam_times = _concat_with_seams(clips, [2, 1], fps=30, transition=0.3, out_path=str(out))
    # 이음매는 세그먼트0(a+b) 끝 근처(실측 duration 기반이라 정확히 2.0은 아님).
    assert len(seam_times) == 1 and abs(seam_times[0] - 2.0) < 0.25
    meta = probe_container(str(out))
    assert meta.duration_sec is not None
    assert abs(meta.duration_sec - 2.7) < 0.25


def test_concat_with_seams_falls_back_to_hard_concat(tmp_path):
    # 세그먼트 1개면 xfade 없이 하드 concat, seam_times 빈 리스트.
    clips = [_clip(tmp_path, "a", 1.0), _clip(tmp_path, "b", 1.0)]
    out = tmp_path / "flat.mp4"
    assert _concat_with_seams(clips, [2], fps=30, transition=0.3, out_path=str(out)) == []
    meta = probe_container(str(out))
    assert meta.duration_sec is not None
    assert abs(meta.duration_sec - 2.0) < 0.4  # 줄지 않는다(하드컷)


def _audio(tmp_path, name, dur):
    import subprocess

    out = tmp_path / f"{name}.m4a"
    # 사인톤(무음 아님) — loudnorm이 완전 무음에선 NaN을 내므로 실제 소리가 있는 트랙을 만든다.
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=44100:duration={dur}",
         "-c:a", "aac", str(out)],
        check=True, capture_output=True,
    )
    return str(out)


def test_output_length_capped_to_video_not_audio(tmp_path):
    # 회귀 방지: BGM/voice가 영상보다 길어도 결과는 '영상 길이'로 고정된다(프리즈 꼬리에 소리가
    # 깔리는 버그 방지). 1초 영상 + 3초 BGM + 3초 voice -> 결과는 ~1초.
    mats = Materials(
        shot_clips=[_clip(tmp_path, "v", 1.0)],
        bgm_audio=_audio(tmp_path, "bgm", 3.0),
        voice_audio=_audio(tmp_path, "voice", 3.0),
    )
    out = tmp_path / "final.mp4"
    assemble(mats, InputMeta(width=540, height=960), str(out))
    meta = probe_container(str(out))
    assert meta.duration_sec is not None
    assert meta.duration_sec < 1.5  # 3초 오디오로 늘어나지 않는다(영상 1초에 맞춤)


def test_assemble_crossfades_two_segments(tmp_path):
    # segment_sizes가 있으면 경계 xfade로 타임라인이 줄어든다(2초 - 0.3 = 1.7초).
    mats = Materials(
        shot_clips=[_clip(tmp_path, "a", 1.0), _clip(tmp_path, "b", 1.0)],
        segment_sizes=[1, 1],
    )
    out = tmp_path / "final.mp4"
    assemble(mats, InputMeta(width=540, height=960), str(out))
    meta = probe_container(str(out))
    assert meta.duration_sec is not None
    assert abs(meta.duration_sec - 1.7) < 0.25
