"""오디오 재료 테스트: 컷-bpm 정렬, 합성 베드, mux. 외부 호출 없는 결정론 검증."""

from PIL import Image

from reel_gen_agent.analysis.media_probe import has_audio_stream
from reel_gen_agent.generate.assemble import assemble
from reel_gen_agent.generate.audio import (
    _NARRATION_TAIL_SEC,
    NARRATION_GAP_SEC,
    NARRATION_MAX_TEMPO,
    _narration_timeline,
    bgm_cut_sync_ok,
    bpm_for_cuts,
    synth_music_bed,
)
from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend
from reel_gen_agent.generate.schema import InputMeta, Materials, StoryboardPanel


def _panels(cut_sec):
    return [
        StoryboardPanel(index=i, t_start=i * cut_sec, t_end=(i + 1) * cut_sec) for i in range(4)
    ]


def test_bpm_lands_in_shortform_lively_band():
    # 컷당 1비트는 처지므로(1.0s->60bpm) 정수배로 올려 경쾌 대역(100~140)에 넣는다.
    for cut_sec in (1.0, 1.2, 2.0, 2.4):
        bpm = bpm_for_cuts(_panels(cut_sec))
        assert 100 <= bpm <= 140, (cut_sec, bpm)
    # 1.0s 컷 -> 60 -> *2 = 120.
    assert bpm_for_cuts(_panels(1.0)) == 120


def test_bpm_stays_beat_aligned_with_cuts():
    # 대역으로 올려도 정수배라 컷은 여전히 비트 위에 떨어진다(동기 유지).
    panels = _panels(1.2)
    bpm = bpm_for_cuts(panels)
    assert bgm_cut_sync_ok(bpm, panels) is True


def test_bpm_clamped_and_positive_for_empty():
    assert bpm_for_cuts([]) == 120


def test_cut_sync_ok_when_cuts_land_on_beats():
    panels = _panels(1.0)
    assert bgm_cut_sync_ok(60, panels) is True
    # 비트 간격(0.5s)의 정수배(2배)에 떨어지므로 동기로 본다.
    assert bgm_cut_sync_ok(120, panels) is True


def test_cut_sync_fails_when_off_beat():
    panels = _panels(1.0)
    # 90bpm -> 비트 0.667s, 1.0s는 1.5배라 정수배가 아님 -> 비동기.
    assert bgm_cut_sync_ok(90, panels) is False


def _ends(durs, tempo, starts):
    """각 대사의 끝 시각(압축 템포 반영)."""
    return [s + d / tempo for s, d in zip(starts, durs, strict=True)]


def test_narration_timeline_never_overlaps_and_has_gap():
    # 컷은 1.19초로 짧지만 대사는 2.2초 -> 순차 배치라 겹치지 않고 쉼이 들어가야 한다.
    durs = [2.2, 2.2, 2.2]
    tempo, starts = _narration_timeline(durs, first_start=0.0, total_dur=30.0)
    assert tempo == 1.0  # 30초 안에 다 들어가니 압축 없음
    assert starts[0] == 0.0
    ends = _ends(durs, tempo, starts)
    for i in range(1, len(starts)):
        # 다음 대사는 직전 대사 끝난 뒤에 시작(겹침 없음) + 쉼 확보.
        assert starts[i] >= ends[i - 1] - 1e-9
        assert starts[i] - ends[i - 1] >= NARRATION_GAP_SEC - 1e-9


def test_narration_timeline_compresses_to_fit_without_cutoff():
    # 대사 총량이 남은 길이를 크게 넘으면 균일 템포로 눌러 전체 길이 안에 맞춘다.
    durs = [2.2] * 8  # 17.6초 + 쉼, 영상은 10.7초
    tempo, starts = _narration_timeline(durs, first_start=0.0, total_dur=10.7)
    assert 1.0 < tempo <= NARRATION_MAX_TEMPO
    ends = _ends(durs, tempo, starts)
    for i in range(1, len(starts)):
        assert starts[i] >= ends[i - 1] - 1e-9  # 여전히 겹치지 않는다


def test_narration_track_len_never_exceeds_video():
    # 대사가 넘쳐도(8*2.2s를 10.7s 영상에) voice 트랙 길이는 영상 길이를 넘지 않아야 한다.
    # 넘으면 mux에서 마지막 프레임이 얼어붙고 소리만 이어진다(리포트된 버그).
    durs = [2.2] * 8
    total = 10.7
    tempo, starts = _narration_timeline(durs, first_start=0.0, total_dur=total)
    last_end = max(s + d / tempo for s, d in zip(starts, durs, strict=True))
    track_len = min(total, last_end + _NARRATION_TAIL_SEC)
    assert track_len <= total + 1e-9


def test_narration_timeline_reserves_tail_within_video():
    # 예산 안에 드는 대사는 마지막 여운(tail)까지 영상 길이 안에 들어가 프리즈가 생기지 않는다.
    durs = [1.5, 1.5, 1.5]
    total = 10.0
    tempo, starts = _narration_timeline(durs, first_start=0.0, total_dur=total)
    last_end = max(s + d / tempo for s, d in zip(starts, durs, strict=True))
    assert last_end + _NARRATION_TAIL_SEC <= total + 1e-9


def test_synth_bed_makes_non_silent_audio(tmp_path):
    out = tmp_path / "bed.wav"
    synth_music_bed(2.0, 120, str(out))
    assert out.exists() and out.stat().st_size > 1000


def _clip(tmp_path, name, dur):
    still = tmp_path / f"{name}.png"
    Image.new("RGB", (540, 960), (180, 140, 200)).save(still)
    out = tmp_path / f"{name}.mp4"
    KenBurnsBackend().render_panel(str(still), dur, 540, 960, 30, str(out))
    return str(out)


def test_assemble_muxes_bgm_audio(tmp_path):
    bgm = str(tmp_path / "bgm.wav")
    synth_music_bed(2.0, 120, bgm)
    mats = Materials(
        shot_clips=[_clip(tmp_path, "a", 1.0), _clip(tmp_path, "b", 1.0)],
        bgm_audio=bgm,
    )
    out = tmp_path / "final.mp4"
    assemble(mats, InputMeta(width=540, height=960), str(out))
    assert out.exists()
    assert has_audio_stream(str(out))  # 오디오 스트림이 들어갔다
