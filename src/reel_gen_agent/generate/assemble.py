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


def _overlay_subtitle(
    clip: str, sub_png: str, width: int, height: int, fps: int, out_path: str
) -> str:
    """클립 위에 자막 PNG(투명)를 전 구간 덮어 굽는다. 오디오는 그대로 복사한다."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        clip,
        "-i",
        sub_png,
        "-filter_complex",
        "[0:v][1:v]overlay=0:0:format=auto[v]",
        "-map",
        "[v]",
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


def _mux_audio(video_path: str, audio_tracks: list[str], out_path: str) -> str:
    """영상에 오디오 트랙(들)을 입힌다. 여러 개면 amix로 섞는다. 영상 길이에 맞춰 자른다."""
    cmd = ["ffmpeg", "-y", "-i", video_path]
    for track in audio_tracks:
        cmd += ["-i", track]
    if len(audio_tracks) == 1:
        amap = "[1:a]volume=1[aout]"
    else:
        inputs = "".join(f"[{i + 1}:a]" for i in range(len(audio_tracks)))
        amap = f"{inputs}amix=inputs={len(audio_tracks)}:duration=longest[aout]"
    cmd += [
        "-filter_complex",
        amap,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def assemble(materials: Materials, meta: InputMeta, out_path: str) -> str:
    if not materials.shot_clips:
        raise ValueError("assemble: shot_clips is empty")

    # 자막 PNG가 패널별로 갖춰지면 각 클립 위에 구워 넣는다(개수 안 맞으면 건너뛴다).
    clips = materials.shot_clips
    subs = materials.subtitle_pngs
    if subs and len(subs) == len(clips):
        overlaid: list[str] = []
        sub_dir = Path(tempfile.mkdtemp(prefix="reel_subs_"))
        for i, (clip, sub) in enumerate(zip(clips, subs, strict=True)):
            out = str(sub_dir / f"ov_{i}.mp4")
            _overlay_subtitle(clip, sub, meta.width, meta.height, meta.fps, out)
            overlaid.append(out)
        clips = overlaid

    audio_tracks = [t for t in (materials.bgm_audio, materials.voice_audio) if t]
    if not audio_tracks:
        # 오디오 재료가 없으면 concat 결과(무음 트랙 포함)를 그대로 쓴다.
        return _concat(clips, meta.fps, out_path)

    # 오디오가 있으면 임시 영상으로 concat한 뒤 BGM/voice를 입혀 최종을 만든다.
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        video_only = tmp.name
    _concat(clips, meta.fps, video_only)
    return _mux_audio(video_only, audio_tracks, out_path)
