"""통합 라우드니스(LUFS)와 피크를 측정한다.

conformance 게이트의 볼륨 적절성 체크에 쓴다. ITU-R BS.1770의 K-weighting을 적용한
게이트 없는 통합 라우드니스를 낸다. 방송 컴플라이언스 도구가 아니라 "너무 작거나 큰가,
클리핑하나"를 보는 새너티 측정이라 게이팅은 생략한다. 무거운 의존성을 더하지 않으려고
scipy.signal(librosa가 이미 의존)로 직접 필터링한다.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# K-weighting 계수는 48kHz 기준이라 오디오를 48k로 추출한다.
_KW_SR = 48000

# ITU-R BS.1770 K-weighting 2단 필터(48kHz).
_STAGE1_B = [1.53512485958697, -2.69169618940638, 1.19839281085285]
_STAGE1_A = [1.0, -1.69065929318241, 0.73248077421585]
_STAGE2_B = [1.0, -2.0, 1.0]
_STAGE2_A = [1.0, -1.99004745483398, 0.99007225036621]

# 측정 불가/무음일 때 돌려줄 바닥값(dB).
_FLOOR_DB = -120.0


@dataclass
class Loudness:
    """통합 라우드니스(LUFS)와 샘플 피크(dBFS). 측정 불가 시 measured=False."""

    lufs: float
    peak_dbfs: float
    measured: bool


def _extract_wav_48k(path: str, out_path: str) -> bool:
    """ffmpeg로 오디오를 48kHz 모노 wav로 추출한다. 오디오가 없으면 False."""
    cmd = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-i",
        path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(_KW_SR),
        out_path,
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def measure_loudness(path: str) -> Loudness:
    """영상/오디오 파일의 통합 라우드니스와 피크를 측정한다.

    오디오가 없거나 디코딩이 실패하면 measured=False로 반환한다(게이트가 죽지 않게).
    """
    import librosa
    from scipy.signal import lfilter

    with tempfile.TemporaryDirectory() as tmp:
        wav = str(Path(tmp) / "audio.wav")
        if not _extract_wav_48k(path, wav):
            return Loudness(lufs=_FLOOR_DB, peak_dbfs=_FLOOR_DB, measured=False)
        try:
            y, _ = librosa.load(wav, sr=_KW_SR, mono=True)
        except Exception:
            return Loudness(lufs=_FLOOR_DB, peak_dbfs=_FLOOR_DB, measured=False)

    if y.size == 0:
        return Loudness(lufs=_FLOOR_DB, peak_dbfs=_FLOOR_DB, measured=False)

    peak = float(np.max(np.abs(y)))
    peak_dbfs = 20 * np.log10(peak) if peak > 0 else _FLOOR_DB

    # K-weighting 2단 필터를 차례로 적용한다.
    filtered = lfilter(_STAGE1_B, _STAGE1_A, y)
    filtered = lfilter(_STAGE2_B, _STAGE2_A, filtered)
    lufs = _gated_loudness(np.asarray(filtered, dtype=np.float64), _KW_SR)

    return Loudness(lufs=round(lufs, 2), peak_dbfs=round(peak_dbfs, 2), measured=True)


def _block_powers(filtered: np.ndarray, sr: int) -> np.ndarray:
    """400ms 블록(100ms 스텝)별 평균 파워. 게이팅 입력."""
    block = int(0.4 * sr)
    step = int(0.1 * sr)
    if block <= 0 or len(filtered) < block:
        return np.array([float(np.mean(filtered**2))]) if len(filtered) else np.array([])
    starts = range(0, len(filtered) - block + 1, step)
    return np.array([float(np.mean(filtered[s : s + block] ** 2)) for s in starts])


def _gated_loudness(filtered: np.ndarray, sr: int) -> float:
    """BS.1770 게이팅(절대 -70 LUFS + 상대 -10 LU)으로 통합 라우드니스를 낸다.

    게이팅 없는 평균은 무음/정적 구간 때문에 라우드니스를 과소평가한다. 블록 단위로 조용한
    구간을 걸러내야 음성 위주 UGC도 실제에 가깝게 측정된다.
    """
    powers = _block_powers(filtered, sr)
    powers = powers[powers > 0]
    if powers.size == 0:
        return _FLOOR_DB

    block_loud = -0.691 + 10 * np.log10(powers)

    # 절대 게이트: -70 LUFS 미만 블록 제거.
    abs_kept = powers[block_loud > -70.0]
    if abs_kept.size == 0:
        abs_kept = powers

    # 상대 게이트: 절대 게이트 통과분의 평균 라우드니스 - 10 LU 미만 블록 제거.
    abs_mean_loud = -0.691 + 10 * np.log10(float(np.mean(abs_kept)))
    rel_thresh = abs_mean_loud - 10.0
    final = abs_kept[(-0.691 + 10 * np.log10(abs_kept)) > rel_thresh]
    if final.size == 0:
        final = abs_kept

    return float(-0.691 + 10 * np.log10(float(np.mean(final))))
