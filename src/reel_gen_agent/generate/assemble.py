"""결정론 조립. 자막 오버레이 + 샷 클립 concat + 오디오 mux -> final.mp4.

같은 Materials는 같은 결과를 낸다(재현성). 컨테이너/코덱은 trd.md 가드레일(mp4/H.264/AAC).
패널별 자막 PNG가 있으면 각 클립 위에 입히고, BGM/voice가 있으면 영상 위에 믹스한다.
둘 다 없으면 무음 트랙으로 둔다.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .schema import InputMeta, Materials


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
    video_len = _duration(video_path)
    voice_len = _duration(voice) if voice else 0.0
    final = max(video_len, voice_len)
    fade = 0.5
    fade_start = max(0.0, final - fade)
    pad_v = max(0.0, final - video_len)
    has_voiceover = bool(voice)  # 실제 나레이션만 발화로 본다(네이티브 앰비언스는 제외).
    sfx = sfx or []

    cmd = ["ffmpeg", "-y", "-i", video_path]
    chains = [f"[0:v]tpad=stop_mode=clone:stop_duration={pad_v:.3f}[v]"]
    labels: list[str] = []
    # 영상 네이티브 오디오([0:a], Veo가 낸 씬 사운드)는 낮은 앰비언스로만 깐다(주인공이 아니며
    # BGM 덕킹도 트리거하지 않는다). Veo 네이티브가 사실상 무음이면 여기서도 조용히 묻힌다.
    if keep_video_audio:
        chains.append(f"[0:a]apad=whole_dur={final:.3f},atrim=0:{final:.3f},volume=0.30[a0]")
        labels.append("[a0]")
    idx = 1
    if voice:
        cmd += ["-i", voice]
        chains.append(f"[{idx}:a]apad=whole_dur={final:.3f},atrim=0:{final:.3f},volume=1.0[a{idx}]")
        labels.append(f"[a{idx}]")
        idx += 1
    if bgm:
        cmd += ["-i", bgm]
        # 나레이션이 있으면 BGM을 덕킹하되 볼륨은 플랜(music.prominence -> bgm_gain)을 따른다.
        # 나레이션이 없으면 BGM이 주인공이므로 거의 풀 볼륨으로 둔다(music_bed에서 확실히 들리게).
        duck = bgm_gain if (bgm_gain is not None) else 0.45
        vol = duck if has_voiceover else 0.95
        chains.append(
            f"[{idx}:a]apad=whole_dur={final:.3f},atrim=0:{final:.3f},volume={vol}[a{idx}]"
        )
        labels.append(f"[a{idx}]")
        idx += 1
    # SFX: BGM/나레이션이 있으면 그 아래 악센트로 낮게, SFX만 있으면 또렷하게. loudnorm으로 소스별
    # 들쭉날쭉한 레벨을 고르게 맞추고(핫한 훅 riser도 여기서 눌린다), 짧은 페이드인으로 어택을 눅인다.
    sfx_vol = 0.5 if (bgm or has_voiceover) else 0.85
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
    target_i = -16 if has_voiceover else -20
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


def assemble(materials: Materials, meta: InputMeta, out_path: str) -> str:
    if not materials.shot_clips:
        raise ValueError("assemble: shot_clips is empty")

    # 1) 세그먼트/컷 클립을 순서대로 이어붙인다(자막 없는 순수 영상).
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        video_only = tmp.name
    _concat(materials.shot_clips, meta.fps, video_only)

    # 2) 자막 PNG가 있으면 최종 타임라인의 각 구간(spans)에 시간 기반으로 덮는다.
    subs = materials.subtitle_pngs
    spans = materials.subtitle_spans
    if subs and spans and len(subs) == len(spans):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            subbed = tmp.name
        _overlay_subtitles_timed(video_only, subs, spans, meta.fps, subbed)
        video_only = subbed

    # 3) 오디오가 없으면 그대로, 있으면 voice/BGM/SFX/네이티브 음성을 입혀 마감한다.
    #    온카메라 발화(native_audio)는 클립에 음성이 있으므로 BGM이 없어도 그대로 살린다.
    sfx = list(zip(materials.sfx_audio, materials.sfx_starts, strict=False))
    if not materials.bgm_audio and not materials.voice_audio and not sfx:
        if materials.native_audio:
            return _mux_audio(video_only, None, None, out_path, keep_video_audio=True)
        return _concat([video_only], meta.fps, out_path)
    return _mux_audio(
        video_only,
        materials.voice_audio,
        materials.bgm_audio,
        out_path,
        keep_video_audio=materials.native_audio,
        bgm_gain=materials.bgm_gain,
        sfx=sfx,
    )
