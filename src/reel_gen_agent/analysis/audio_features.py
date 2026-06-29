"""librosa로 오디오 수치를 뽑는다. 빌드업 vs 평탄, BPM, 인트로 무음 등."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np
import librosa
from librosa.feature.rhythm import tempo as librosa_tempo

from .profile import Music

# RMS 엔벨로프의 후반 평균이 전반 평균보다 이 비율 이상 크면 '빌드업'으로 본다.
BUILD_RATIO_THRESHOLD = 1.4
# 인트로 무음 판정: 이 진폭 미만 구간을 무음으로 본다.
SILENCE_AMPLITUDE = 0.01


def _intro_silence_sec(y: np.ndarray, sr: int) -> float:
    """시작부터 첫 유의미한 소리가 날 때까지의 무음 길이(초)."""
    above = np.where(np.abs(y) >= SILENCE_AMPLITUDE)[0]
    if len(above) == 0:
        return 0.0
    return round(float(above[0]) / sr, 3)


def _dynamics(rms: np.ndarray) -> str:
    """RMS 엔벨로프 전반/후반 평균을 비교해 빌드업인지 평탄인지 판정한다."""
    if len(rms) < 4:
        return "flat"
    half = len(rms) // 2
    first_half = float(np.mean(rms[:half]))
    second_half = float(np.mean(rms[half:]))
    if first_half <= 1e-9:
        return "build" if second_half > SILENCE_AMPLITUDE else "flat"
    return "build" if (second_half / first_half) >= BUILD_RATIO_THRESHOLD else "flat"


def _extract_wav(path: str, out_path: str) -> bool:
    """ffmpeg로 오디오 트랙만 22.05kHz 모노 wav로 추출한다.

    librosa가 mp4를 직접 디코딩하면 deprecated audioread 경로를 타므로,
    표준 wav로 한 번 떨궈서 soundfile 경로로 안정적으로 읽게 한다.
    오디오 스트림이 없으면 ffmpeg가 실패하고 False를 반환한다.
    """
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-i", path,
        "-vn", "-ac", "1", "-ar", "22050",
        out_path,
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def extract_audio_features(path: str) -> Music:
    """영상의 오디오 트랙에서 음악 수치를 뽑는다.

    오디오가 없거나 디코딩 실패 시 빈 Music을 반환한다(정형 계층은 죽지 않는다).
    """
    with tempfile.TemporaryDirectory() as tmp:
        wav = str(Path(tmp) / "audio.wav")
        if not _extract_wav(path, wav):
            return Music()
        try:
            y, sr = librosa.load(wav, sr=None, mono=True)
        except Exception:
            return Music()

    if y.size == 0:
        return Music()

    rms = librosa.feature.rms(y=y)[0]
    tempo = librosa_tempo(y=y, sr=sr)
    bpm = round(float(tempo[0]), 1) if len(tempo) else None

    # 연속성: 무음 프레임 비율이 낮으면 연속 BGM으로 본다.
    silent_ratio = float(np.mean(rms < SILENCE_AMPLITUDE))
    continuous = silent_ratio < 0.2

    return Music(
        continuous=continuous,
        bpm=bpm,
        dynamics=_dynamics(rms),
        intro_silence_sec=_intro_silence_sec(y, sr),
    )
