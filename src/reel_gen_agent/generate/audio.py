"""오디오 재료: BGM(컷 주기에 bpm 정렬)과 voice(나레이션)를 만든다.

BGM 선정과 컷-음악 동기는 매우 중요하다([ai-model-records.md] 5번). 컷 평균 길이로 목표
bpm을 잡아 BGM에 요청하고, 컷-음악 동기를 별도로 검증한다(`bgm_cut_sync_ok`).

voice 정책([ADR.md] ADR-0012):
- voiceover(나레이션, 기본): 별도 TTS로 생성해 mux한다(ElevenLabs/Google TTS).
- on_camera: 영상 모델이 발화를 품고 나오므로 별도 voice를 만들지 않는다.

키가 없으면 BGM은 합성 베드(ffmpeg 톤)로 대체해 무음을 피하고, voice는 생략한다.
실제 Lyria/ElevenLabs는 주입 클라이언트로 키가 있을 때 쓴다.
"""

from __future__ import annotations

import subprocess
from typing import Protocol

from .schema import StoryboardPanel


def bpm_for_cuts(panels: list[StoryboardPanel], beats_per_cut: int = 1) -> int:
    """평균 컷 길이로 목표 bpm을 잡는다. 컷이 비트 위에 떨어지도록.

    bpm = 60 / 평균_컷_초 * beats_per_cut. 통상 30~200 범위로 클램프.
    """
    durs = [(p.t_end or 0.0) - (p.t_start or 0.0) for p in panels]
    durs = [d for d in durs if d > 0]
    if not durs:
        return 120
    mean = sum(durs) / len(durs)
    bpm = round(60.0 / mean * beats_per_cut)
    return max(30, min(200, bpm))


def bgm_cut_sync_ok(bpm: int, panels: list[StoryboardPanel], tol: float = 0.15) -> bool:
    """컷 주기가 비트(또는 비트의 정수배)에 맞는지 검증한다.

    각 컷 길이가 비트 간격(60/bpm)의 정수배에 tol(비율) 안으로 떨어지면 동기로 본다.
    """
    if bpm <= 0:
        return False
    beat = 60.0 / bpm
    durs = [(p.t_end or 0.0) - (p.t_start or 0.0) for p in panels]
    durs = [d for d in durs if d > 0]
    if not durs:
        return False
    for d in durs:
        ratio = d / beat
        nearest = round(ratio)
        if nearest < 1 or abs(ratio - nearest) > tol:
            return False
    return True


def synth_music_bed(duration_sec: float, bpm: int, out_path: str) -> str:
    """키 없이 쓰는 합성 BGM 베드. bpm에 맞춘 트레몰로 톤(무음 회피용 플레이스홀더).

    loudnorm으로 -18 LUFS에 정규화해 conformance 볼륨 범위(-30~-5 LUFS) 안에 들어가게 한다.
    """
    f_trem = max(0.1, bpm / 60.0)
    af = f"tremolo=f={f_trem}:d=0.5,loudnorm=I=-18:TP=-2:LRA=11"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=196:duration={duration_sec}",
        "-af",
        af,
        "-c:a",
        "pcm_s16le",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


class MusicClient(Protocol):
    """BGM 생성 백엔드. 기본은 Lyria 3(Clip)으로 한 번에 30초까지 생성한다.

    대부분의 숏폼은 30초 이하라 Clip으로 충분하다. `duration_sec`가 30을 넘으면
    30초 상한을 넘는 트랙이 필요한 경우이므로 Lyria 3 Pro로 승격해야 한다.
    """

    def generate(self, prompt: str, bpm: int, duration_sec: float, out_path: str) -> str: ...


class VoiceClient(Protocol):
    def synthesize(self, text: str, voice_desc: str, out_path: str) -> str: ...
