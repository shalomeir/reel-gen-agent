"""결정론 조립. 자막 오버레이 + 샷 클립 concat + 오디오 mux -> final.mp4.

같은 Materials는 같은 결과를 낸다(재현성). 컨테이너/코덱은 trd.md 가드레일(mp4/H.264/AAC).
패널별 자막 PNG가 있으면 각 클립 위에 입히고, BGM/voice가 있으면 영상 위에 믹스한다.
둘 다 없으면 무음 트랙으로 둔다.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from .schema import InputMeta, Materials

# 세그먼트 경계 크로스페이드 길이(초). 세그먼트 안 beat-cut은 하드컷을 유지하고, 독립 생성된
# 세그먼트끼리 붙는 이음매에만 이 길이로 xfade(영상)+acrossfade(오디오)를 건다. 0이면 끈다.
_SEG_XFADE_DEFAULT = 0.3


def _seg_xfade() -> float:
    """세그먼트 경계 크로스페이드 길이(초). REEL_SEG_XFADE로 조정, 음수/비정상은 기본값."""
    raw = os.environ.get("REEL_SEG_XFADE")
    if raw is None:
        return _SEG_XFADE_DEFAULT
    try:
        v = float(raw)
    except ValueError:
        return _SEG_XFADE_DEFAULT
    return max(0.0, v)


def _overlay_subtitles_timed(
    clip: str,
    subs: list[str],
    spans: list[list[float]],
    fps: int,
    out_path: str,
) -> str:
    """최종 타임라인에 자막 PNG들을 각자 [start, end] 구간에만 덮어 굽는다.

    세그먼트가 2개든 컷이 9개든, 자막은 계획된 패널 구간(초)에 시간 기반으로 뜬다.
    각 자막을 enable='between(t,s,e)'로 그 구간에만 켠다. 오디오는 그대로 복사한다.
    """
    cmd = ["ffmpeg", "-y", "-i", clip]
    for sub in subs:
        cmd += ["-i", sub]
    chains: list[str] = []
    prev = "[0:v]"
    for i, (start, end) in enumerate(spans):
        out_label = f"[v{i}]"
        chains.append(
            f"{prev}[{i + 1}:v]overlay=0:0:format=auto:"
            f"enable='between(t,{start:.3f},{end:.3f})'{out_label}"
        )
        prev = out_label
    cmd += [
        "-filter_complex",
        ";".join(chains),
        "-map",
        prev,
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-c:a",
        "copy",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _concat(shot_clips: list[str], fps: int, out_path: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for clip in shot_clips:
            f.write(f"file '{Path(clip).resolve()}'\n")
        listfile = f.name
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        listfile,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-c:a",
        "aac",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def _group_by_sizes(items: list[str], sizes: list[int]) -> list[list[str]] | None:
    """flat 리스트를 sizes대로 세그먼트 그룹으로 나눈다. sizes가 안 맞으면 None(하드컷 폴백)."""
    if not sizes or sum(sizes) != len(items):
        return None
    groups: list[list[str]] = []
    i = 0
    for n in sizes:
        if n > 0:
            groups.append(items[i : i + n])
        i += n
    return groups


def _shift_spans_for_seams(
    spans: list[list[float]], seam_times: list[float], transition: float
) -> list[list[float]]:
    """세그먼트 경계 xfade로 타임라인이 이음매마다 transition만큼 줄어든다. 원본 spans를 줄어든
    타임라인으로 옮긴다. span 시작 이전에 있던 이음매 개수 x transition만큼 당긴다(순수 함수)."""
    out: list[list[float]] = []
    for s, e in spans:
        before = sum(1 for t in seam_times if t <= s + 1e-6)
        shift = before * transition
        out.append([max(0.0, s - shift), max(0.0, e - shift)])
    return out


def _native_ambience_gain(
    native_audio: bool, native_speech: bool, has_bgm: bool, has_voice: bool
) -> float | None:
    """네이티브 오디오(영상 씬 사운드) 볼륨 게인을 정한다(순수 함수). None이면 기본(0.30).

    - 온카메라 발화(native_speech)면 네이티브가 곧 '목소리'다 -> 또렷하게 1.0으로 올린다(BGM은
      발화 아래로 덕킹된다, _mux_audio가 처리).
    - 발화가 아닌 씬 앰비언스이고 BGM이 있으면: music_bed(나레이션 없음)에선 BGM이 주인공이라
      앰비언스를 끄고(0.0), 나레이션 아래선 아주 낮게(0.12) 깐다 -> 경계 스냅·BGM 충돌 제거.
    - 그 밖(앰비언스인데 BGM 없음)은 기본(None=0.30).
    """
    if not native_audio:
        return None
    if native_speech:
        return 1.0
    if has_bgm:
        return 0.0 if not has_voice else 0.12
    return None


def _concat_with_seams(
    shot_clips: list[str], segment_sizes: list[int], fps: int, transition: float, out_path: str
) -> list[float]:
    """세그먼트 안은 하드컷, 세그먼트 경계에만 xfade(영상)+acrossfade(오디오)로 잇는다.

    독립 생성된 세그먼트끼리 툭 끊기는 점프(그림 + Kling 씬 앰비언스)를 눅인다. 세그먼트 안
    beat-cut은 같은 영상을 자른 거라 하드컷을 유지해 리듬을 살린다. 원본 타임라인 기준 이음매
    시각 리스트를 돌려주어(자막 span 보정용), assemble이 줄어든 타임라인에 맞춘다.

    세그먼트가 2개 미만이거나 transition<=0이거나 경계 정보가 없거나, 세그먼트 하나가
    transition보다 짧아 xfade가 불가하면 하드 concat으로 폴백하고 빈 리스트를 돌려준다.
    """
    groups = _group_by_sizes(shot_clips, segment_sizes)
    if transition <= 0 or groups is None or len(groups) < 2:
        _concat(shot_clips, fps, out_path)
        return []

    # 1) 세그먼트 안은 하드컷으로 이어 세그먼트 클립 하나로 만든다.
    seg_files: list[str] = []
    seg_durs: list[float] = []
    for group in groups:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            seg_path = tmp.name
        _concat(group, fps, seg_path)
        seg_files.append(seg_path)
        seg_durs.append(_duration(seg_path))

    # 세그먼트가 transition보다 짧으면 xfade가 불가하다 -> 안전하게 하드 concat 폴백.
    if any(d <= transition for d in seg_durs):
        _concat(shot_clips, fps, out_path)
        return []

    # 2) 세그먼트 경계마다 xfade(영상)+acrossfade(오디오). offset은 누적 합성 길이 - transition.
    cmd = ["ffmpeg", "-y"]
    for sf in seg_files:
        cmd += ["-i", sf]
    v_chains: list[str] = []
    a_chains: list[str] = []
    prev_v, prev_a = "[0:v]", "[0:a]"
    acc = seg_durs[0]
    seam_times: list[float] = []
    for i in range(1, len(seg_files)):
        seam_times.append(acc)  # 원본 타임라인에서 이 이음매가 시작하는 시각
        offset = acc - transition
        out_v, out_a = f"[vx{i}]", f"[ax{i}]"
        v_chains.append(
            f"{prev_v}[{i}:v]xfade=transition=fade:duration={transition:.3f}:"
            f"offset={offset:.3f}{out_v}"
        )
        a_chains.append(f"{prev_a}[{i}:a]acrossfade=d={transition:.3f}{out_a}")
        prev_v, prev_a = out_v, out_a
        acc = acc + seg_durs[i] - transition
    filter_complex = ";".join(v_chains + a_chains)
    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        prev_v,
        "-map",
        prev_a,
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return seam_times


def _duration(path: str) -> float:
    """미디어 길이(초). 실패하면 0.0."""
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            path,
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _mux_audio(
    video_path: str,
    voice: str | None,
    bgm: str | None,
    out_path: str,
    keep_video_audio: bool = False,
    bgm_gain: float | None = None,
    sfx: list[tuple[str, float]] | None = None,
    loudness_target: float | None = None,
    native_gain: float | None = None,
    native_is_speech: bool = False,
) -> str:
    """영상에 나레이션 voice·BGM·효과음(SFX)을 입힌다. 오디오가 잘리거나 툭 끊기지 않게 마감한다.

    나레이션(voice)은 상류에서 영상 길이에 맞춰 예산화·캡되므로 대개 영상보다 짧거나 같다.
    최종 길이는 max(영상, voice)로 잡되, 혹시 voice가 프레임 반올림 등으로 미세하게 길면 그만큼만
    마지막 프레임을 이어(tpad) 메운다(옛날처럼 긴 프리즈가 생기지 않는다). 끝에 0.5초
    페이드아웃을 걸어 툭 끊기지 않게 한다.

    발화 판정은 '실제 나레이션(voice)'만으로 한다. 영상 네이티브 오디오(keep_video_audio)는
    대개 씬 앰비언스일 뿐(Veo는 거의 무음을 낸다)이라, 이를 발화로 보면 나레이션이 없는
    music_bed 영상에서 BGM이 근거 없이 덕킹돼 안 들린다. 그래서 네이티브 오디오는 낮은
    앰비언스 레이어로만 섞고 BGM 덕킹을 트리거하지 않는다. 나레이션이 없으면 BGM이 주인공이다.

    SFX는 소스 레벨이 제각각(클리핑까지)이라 그대로 얹으면 특정 컷(예: 첫 훅 riser)이 튄다.
    각 SFX를 loudnorm으로 레벨을 고르게 맞추고 짧은 페이드인으로 어택을 눅여, BGM 아래
    악센트로만 들리게 한다. 각자 컷 시작 시각에 지연 배치한다.
    """
    # 최종 길이는 '영상 길이'로 고정한다. 오디오(voice/bgm/sfx)는 여기에 맞춰 trim되어 영상 뒤로
    # 절대 넘치지 않는다. 예전엔 max(영상, voice)라 voice/bgm이 영상보다 길면(모델 정수 duration
    # 반올림, 세그먼트 경계 크로스페이드로 영상이 total_dur보다 짧아짐 등) 영상을 프리즈로 늘려
    # 그 위에 소리가 깔렸다(스틸 프레임에 음악·나레이션 계속). 영상 길이에 맞춰 오디오를 자른다.
    video_len = _duration(video_path)
    final = video_len
    fade = 0.5
    fade_start = max(0.0, final - fade)
    pad_v = 0.0  # 영상을 오디오에 맞춰 늘리지 않는다(프리즈 꼬리 제거).
    has_voiceover = bool(voice)  # 별도 나레이션 트랙(voiceover) 유무.
    # 발화 존재 여부: 별도 나레이션(voiceover) 또는 온카메라 네이티브 발화(integrated). 둘 중
    # 하나라도 있으면 BGM을 덕킹하고 loudnorm을 발화용(-16)으로 맞춰 말소리가 묻히지 않게 한다.
    speech_present = has_voiceover or native_is_speech
    sfx = sfx or []

    cmd = ["ffmpeg", "-y", "-i", video_path]
    chains = [f"[0:v]tpad=stop_mode=clone:stop_duration={pad_v:.3f}[v]"]
    labels: list[str] = []
    # 영상 네이티브 오디오([0:a], 영상 모델이 낸 씬 사운드)는 낮은 앰비언스로만 깐다(주인공이
    # 아니며 BGM 덕킹도 트리거하지 않는다). native_gain으로 볼륨을 조절한다: music_bed에서 Kling
    # 앰비언스가 BGM과 충돌하고 세그먼트 경계에서 스냅하므로, 앰비언스일 땐 아주 낮추거나(0에
    # 가깝게) 끈다(assemble이 판단). None이면 기본 0.30. Veo 네이티브가 무음이면 여기서도 묻힌다.
    native_vol = native_gain if native_gain is not None else 0.30
    if keep_video_audio and native_vol > 0:
        chains.append(
            f"[0:a]apad=whole_dur={final:.3f},atrim=0:{final:.3f},volume={native_vol}[a0]"
        )
        labels.append("[a0]")
    idx = 1
    if voice:
        cmd += ["-i", voice]
        # 나레이션(voiceover)이 너무 튀지 않게 살짝 낮춘다. 이래도 BGM이 발화 아래로 덕킹되고
        # 최종 loudnorm이 발화용(-16)이라 또렷하게 들리되, 예전(1.0)보다 덜 강하게 앉는다.
        chains.append(f"[{idx}:a]apad=whole_dur={final:.3f},atrim=0:{final:.3f},volume=0.85[a{idx}]")
        labels.append(f"[a{idx}]")
        idx += 1
    if bgm:
        cmd += ["-i", bgm]
        # 나레이션이 있으면 BGM을 덕킹하되 볼륨은 플랜(music.prominence -> bgm_gain)을 따른다.
        # 나레이션이 없으면 BGM이 주인공이므로 거의 풀 볼륨으로 둔다(music_bed에서 확실히 들리게).
        duck = bgm_gain if (bgm_gain is not None) else 0.45
        vol = duck if speech_present else 0.95
        chains.append(
            f"[{idx}:a]apad=whole_dur={final:.3f},atrim=0:{final:.3f},volume={vol}[a{idx}]"
        )
        labels.append(f"[a{idx}]")
        idx += 1
    # SFX: BGM/나레이션이 있으면 그 아래 악센트로 낮게, SFX만 있으면 또렷하게. loudnorm으로 소스별
    # 들쭉날쭉한 레벨을 고르게 맞추고(핫한 훅 riser도 여기서 눌린다), 짧은 페이드인으로 어택을 눅인다.
    sfx_vol = 0.5 if (bgm or speech_present) else 0.85
    for clip, start in sfx:
        cmd += ["-i", clip]
        delay_ms = int(max(0.0, start) * 1000)
        chains.append(
            f"[{idx}:a]afade=t=in:d=0.10,loudnorm=I=-24:TP=-3:LRA=11,aresample=44100,"
            f"adelay={delay_ms}|{delay_ms},apad=whole_dur={final:.3f},"
            f"atrim=0:{final:.3f},volume={sfx_vol}[a{idx}]"
        )
        labels.append(f"[a{idx}]")
        idx += 1

    mix = f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0[amx]"
    # 합친 뒤 loudnorm으로 전체 레벨을 목표에 맞춘다(회차마다 체감 볼륨 일정, 클리핑 방지).
    # 나레이션이 있으면 발화가 또렷하도록 -16 LUFS, 순수 음악 베드는 더 조용하게 -20 LUFS로
    # 둔다(음악만 크게 깔리면 시끄럽게 들린다는 피드백). TP -2dB로 인터샘플 클리핑 여유도 준다.
    # loudness_target이 주어지면(verify repair 교정) 그 목표로 정규화하고, 없으면 기본 규칙.
    target_i = loudness_target if loudness_target is not None else (-16 if speech_present else -20)
    norm = f"[amx]loudnorm=I={target_i}:TP=-2:LRA=11[nrm]"
    fade_f = f"[nrm]afade=t=out:st={fade_start:.3f}:d={fade}[aout]"
    filter_complex = ";".join([*chains, mix, norm, fade_f])
    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[aout]",
        "-t",
        f"{final:.3f}",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def assemble(
    materials: Materials,
    meta: InputMeta,
    out_path: str,
    loudness_target: float | None = None,
) -> str:
    if not materials.shot_clips:
        raise ValueError("assemble: shot_clips is empty")

    # 1) 클립을 이어붙인다(자막 없는 순수 영상). 세그먼트 안 beat-cut은 하드컷, 독립 생성된
    #    세그먼트 경계에만 xfade+acrossfade를 걸어 그림·씬 앰비언스 점프를 눅인다. xfade로
    #    타임라인이 이음매마다 줄어들어(seam_times), 뒤 단계의 자막 span을 그만큼 당긴다.
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        video_only = tmp.name
    transition = _seg_xfade()
    seam_times = _concat_with_seams(
        materials.shot_clips, materials.segment_sizes, meta.fps, transition, video_only
    )

    # 2) 자막 PNG가 있으면 최종 타임라인의 각 구간(spans)에 시간 기반으로 덮는다. 경계 xfade로
    #    줄어든 타임라인이면 span도 이음매 개수만큼 당겨 싱크를 맞춘다.
    subs = materials.subtitle_pngs
    spans = materials.subtitle_spans
    if seam_times:
        spans = _shift_spans_for_seams(spans, seam_times, transition)
    if subs and spans and len(subs) == len(spans):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            subbed = tmp.name
        _overlay_subtitles_timed(video_only, subs, spans, meta.fps, subbed)
        video_only = subbed

    # 3) 오디오가 없으면 그대로, 있으면 voice/BGM/SFX/네이티브 음성을 입혀 마감한다.
    #    온카메라 발화(native_audio)는 클립에 음성이 있으므로 BGM이 없어도 그대로 살린다.
    #    네이티브가 씬 앰비언스(발화 아님)이고 BGM이 있으면, music_bed에선 앰비언스를 끄고
    #    (0.0) 나레이션 아래선 아주 낮게(0.12) 깐다 -> BGM 충돌·경계 스냅을 없앤다. 발화
    #    (integrated)이거나 BGM이 없으면 기본대로 보존한다.
    native_gain = _native_ambience_gain(
        materials.native_audio,
        materials.native_speech,
        has_bgm=bool(materials.bgm_audio),
        has_voice=bool(materials.voice_audio),
    )
    sfx = list(zip(materials.sfx_audio, materials.sfx_starts, strict=False))
    if not materials.bgm_audio and not materials.voice_audio and not sfx:
        if materials.native_audio:
            return _mux_audio(
                video_only, None, None, out_path, keep_video_audio=True,
                loudness_target=loudness_target,
                native_gain=native_gain,
                native_is_speech=materials.native_speech,
            )
        return _concat([video_only], meta.fps, out_path)
    return _mux_audio(
        video_only,
        materials.voice_audio,
        materials.bgm_audio,
        out_path,
        keep_video_audio=materials.native_audio,
        bgm_gain=materials.bgm_gain,
        sfx=sfx,
        loudness_target=loudness_target,
        native_gain=native_gain,
        native_is_speech=materials.native_speech,
    )
