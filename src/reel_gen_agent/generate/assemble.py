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


def _mux_audio(video_path: str, voice: str | None, bgm: str | None, out_path: str) -> str:
    """영상에 나레이션 voice와 BGM을 입힌다. 오디오가 잘리거나 툭 끊기지 않게 마감한다.

    최종 길이는 max(영상, voice)라 나레이션이 중간에 잘리지 않는다. 영상이 짧으면 마지막
    프레임을 이어(tpad) 채우고, 끝에 0.5초 페이드아웃을 걸어 툭 끊기지 않게 한다. BGM은
    voice가 있으면 아래로 덕킹해 나레이션이 들리게 한다.
    """
    video_len = _duration(video_path)
    voice_len = _duration(voice) if voice else 0.0
    final = max(video_len, voice_len)
    fade = 0.5
    fade_start = max(0.0, final - fade)
    pad_v = max(0.0, final - video_len)

    cmd = ["ffmpeg", "-y", "-i", video_path]
    chains = [f"[0:v]tpad=stop_mode=clone:stop_duration={pad_v:.3f}[v]"]
    labels: list[str] = []
    idx = 1
    if voice:
        cmd += ["-i", voice]
        chains.append(f"[{idx}:a]apad=whole_dur={final:.3f},atrim=0:{final:.3f},volume=1.0[a{idx}]")
        labels.append(f"[a{idx}]")
        idx += 1
    if bgm:
        cmd += ["-i", bgm]
        vol = 0.28 if voice else 0.85  # voice가 있으면 BGM을 아래로 덕킹
        chains.append(
            f"[{idx}:a]apad=whole_dur={final:.3f},atrim=0:{final:.3f},volume={vol}[a{idx}]"
        )
        labels.append(f"[a{idx}]")
        idx += 1

    mix = f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0[amx]"
    fade_f = f"[amx]afade=t=out:st={fade_start:.3f}:d={fade}[aout]"
    filter_complex = ";".join([*chains, mix, fade_f])
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

    # 3) 오디오가 없으면 그대로, 있으면 voice/BGM을 입혀 마감한다.
    if not materials.bgm_audio and not materials.voice_audio:
        return _concat([video_only], meta.fps, out_path)
    return _mux_audio(video_only, materials.voice_audio, materials.bgm_audio, out_path)
