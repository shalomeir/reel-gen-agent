"""오디오 재료 테스트: 컷-bpm 정렬, 합성 베드, mux. 외부 호출 없는 결정론 검증."""

from PIL import Image

from reel_gen_agent.analysis.media_probe import has_audio_stream
from reel_gen_agent.generate.assemble import assemble
from reel_gen_agent.generate.audio import bgm_cut_sync_ok, bpm_for_cuts, synth_music_bed
from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend
from reel_gen_agent.generate.schema import InputMeta, Materials, StoryboardPanel


def _panels(cut_sec):
    return [
        StoryboardPanel(index=i, t_start=i * cut_sec, t_end=(i + 1) * cut_sec) for i in range(4)
    ]


def test_bpm_for_one_second_cuts_is_60():
    assert bpm_for_cuts(_panels(1.0)) == 60


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
