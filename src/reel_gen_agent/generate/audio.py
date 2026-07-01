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
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from .schema import NarrationLine, StoryboardPanel


def _audio_duration(path: str) -> float:
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


# 대사와 대사 사이 최소 쉼(초). 숨 쉴 틈을 줘 붙어 들리지 않게 한다.
NARRATION_GAP_SEC = 0.15
# 전체 길이에 맞추려 올릴 수 있는 최대 템포. 넘으면 목소리가 부자연스러워 여기서 캡한다.
NARRATION_MAX_TEMPO = 1.6


def _narration_timeline(
    durs: list[float], first_start: float, total_dur: float
) -> tuple[float, list[float]]:
    """대사 길이 목록을 순차 배치 타임라인으로 바꾼다(겹침 없음).

    첫 대사는 first_start에서 시작하고, 각 다음 대사는 직전 대사(압축 후 길이)가 끝나고
    NARRATION_GAP_SEC만큼 쉰 뒤 시작한다. 전체 대사+쉼이 남은 길이를 넘으면 모든 대사에
    같은 템포(최대 NARRATION_MAX_TEMPO)를 걸어 잘리지 않게 압축한다.

    반환: (적용 템포, 각 대사 시작 시각 목록). 시작 시각은 항상 비감소이며 겹치지 않는다.
    """
    anchor = min(total_dur, max(0.0, first_start))
    content = sum(durs) + NARRATION_GAP_SEC * (len(durs) - 1)
    available = max(0.1, total_dur - anchor)
    tempo = min(NARRATION_MAX_TEMPO, content / available) if content > available else 1.0

    starts: list[float] = []
    cursor = anchor
    for dur in durs:
        starts.append(cursor)
        # 다음 대사는 이번 대사(압축 후 길이)가 끝나고 쉼만큼 뒤 -> 겹치지 않는다.
        cursor += dur / tempo + NARRATION_GAP_SEC
    return tempo, starts


def compose_aligned_narration(
    lines: list[NarrationLine],
    panels: list[StoryboardPanel],
    total_dur: float,
    tts: Callable[[str, str], str],
    work_dir: str,
    out_path: str,
) -> str | None:
    """대사를 순차 배치(직전 대사 끝 + 짧은 쉼)해 전체 길이 voice 트랙으로 합성한다.

    각 대사를 TTS한 뒤 스토리보드 순서대로 이어 깐다. 대사는 절대 겹치지 않는다: 다음
    대사는 직전 대사가 끝나고 NARRATION_GAP_SEC만큼 쉰 뒤 시작한다. 첫 대사는 해당 패널
    t_start에서 시작해 영상 도입과 맞춘다. 전체 대사가 total_dur를 넘으면 전 대사에 같은
    템포(최대 NARRATION_MAX_TEMPO)를 걸어 잘리지 않게 맞춘다(넘침 대신 균일 압축).
    """
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    starts = {p.index: (p.t_start or 0.0) for p in panels}

    # 스토리보드 순서(패널 t_start, 그다음 index)대로 TTS하고 길이를 잰다.
    made: list[tuple[str, float, float]] = []  # (clip, dur, panel_start)
    for line in sorted(lines, key=lambda ln: (starts.get(ln.panel_index, 0.0), ln.panel_index)):
        if not line.text.strip():
            continue
        clip = str(work / f"nl_{line.panel_index}.mp3")
        try:
            tts(line.text.strip(), clip)
        except Exception:
            continue
        dur = _audio_duration(clip)
        if dur <= 0:
            continue
        made.append((clip, dur, max(0.0, starts.get(line.panel_index, 0.0))))

    if not made:
        return None

    # 첫 대사는 그 패널 t_start에서 시작. 순차 배치 타임라인을 계산한다(겹침 없음).
    tempo, line_starts = _narration_timeline(
        [dur for _, dur, _ in made], made[0][2], total_dur
    )

    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []
    for i, ((clip, _dur, _), start) in enumerate(zip(made, line_starts)):
        chain = f"[{i + 1}:a]"
        if tempo > 1.0:
            chain += f"atempo={tempo:.3f},"
        delay_ms = int(start * 1000)
        filters.append(f"{chain}adelay={delay_ms}|{delay_ms}[d{i}]")
        labels.append(f"[d{i}]")
        inputs.append(clip)

    if not labels:
        return None

    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={total_dur:.3f}"]
    for clip in inputs:
        cmd += ["-i", clip]
    # 무음 베드([0])와 지연 배치한 대사들을 섞고 total_dur로 자른다.
    mix = f"[0:a]{''.join(labels)}amix=inputs={len(labels) + 1}:normalize=0:duration=first[aout]"
    cmd += [
        "-filter_complex",
        ";".join([*filters, mix]),
        "-map",
        "[aout]",
        "-t",
        f"{total_dur:.3f}",
        "-c:a",
        "pcm_s16le",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


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
