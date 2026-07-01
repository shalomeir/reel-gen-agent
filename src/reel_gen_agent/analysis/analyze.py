"""analyze_video: 정형 계층 + 비정형 계층을 묶어 VideoProfile을 만든다.

세 소비처(레퍼런스 분석, URL 큐레이션, 생성물 Gate)가 호출하는 공통 엔진.
CLI로는 `reel-gen analyze <video> [--out profiles/x.json]` 로 호출한다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .audio_features import extract_audio_features
from .cut_detector import detect_cuts
from .gemini_describe import describe
from .media_probe import probe_container
from .profile import Source, VideoProfile
from .visual_features import extract_visual_features

# 비트 동기 여부 라벨. 자동 추론값이 없으면 meaning_based를 기본 가정으로 둔다.
DEFAULT_CUT_SYNC = "meaning_based"


def _load_env() -> None:
    """레포 루트의 .env를 찾아 로드한다. 키를 환경에 채운다.

    이 파일에서 위로 올라가며 pyproject.toml 또는 .git가 있는 디렉터리를 레포
    루트로 보고 그곳의 .env를 읽는다.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            env_path = parent / ".env"
            if env_path.exists():
                load_dotenv(env_path, override=False)
            return


def analyze_video(
    path: str,
    url: str | None = None,
    use_gemini: bool = True,
) -> VideoProfile:
    """영상 한 편을 분석해 VideoProfile을 반환한다.

    정형 계층(ffprobe/PySceneDetect/librosa/OpenCV)은 항상 돌고,
    비정형 계층(Gemini)은 use_gemini=True이고 키가 있을 때만 채운다.
    """
    _load_env()
    path = str(path)

    # --- 정형 계층 ---
    container = probe_container(path)
    cut = detect_cuts(path)
    if cut.count and cut.sync is None:
        cut.sync = DEFAULT_CUT_SYNC
    music = extract_audio_features(path)
    palette_hex, brightness, contrast = extract_visual_features(path)

    profile = VideoProfile(container=container, cut=cut, music=music)
    profile.visual.palette = palette_hex
    profile.visual.brightness = brightness
    profile.visual.contrast = contrast
    profile.source = Source(path=path, url=url)

    # --- 비정형 계층 (Gemini) ---
    if use_gemini:
        desc = describe(path, container.duration_sec)
        _merge_gemini(profile, desc)

    return profile


def _merge_gemini(profile: VideoProfile, desc) -> None:
    """Gemini 묘사 결과를 VideoProfile에 병합한다.

    정형 계층이 이미 채운 수치(밝기·bpm 등)는 보존하고, 비정형 필드만 덮는다.
    visual.palette는 OpenCV의 hex가 정량값이라 유지하고, Gemini의 색 무드 단어는
    뒤에 덧붙여 사람이 읽기 쉽게 한다.
    """
    if desc.visual_palette:
        # hex 팔레트 뒤에 Gemini의 색 무드 단어를 덧붙인다.
        profile.visual.palette = profile.visual.palette + desc.visual_palette
    profile.visual.motion = desc.visual_motion

    profile.subtitle = desc.subtitle
    profile.voice = desc.voice

    # 음악: dynamics는 librosa 측정값(정형)을 우선하고, 비었을 때만 Gemini로 채운다.
    # bpm/연속성/무음도 librosa 유지. beat_synced는 librosa가 못 내므로 Gemini로 채운다.
    if desc.music_dynamics and profile.music.dynamics is None:
        profile.music.dynamics = desc.music_dynamics
    if desc.music_beat_synced is not None:
        profile.music.beat_synced = desc.music_beat_synced
        # 컷 동기 라벨도 음악 비트 동기 여부와 일치시킨다.
        profile.cut.sync = "beat_based" if desc.music_beat_synced else "meaning_based"

    profile.hook = desc.hook
    profile.subject = desc.subject
    profile.product = desc.product
    profile.tone = desc.tone
    profile.narrative_arc = desc.narrative_arc
    profile.description = desc.description


def _main() -> int:
    parser = argparse.ArgumentParser(description="영상을 분석해 VideoProfile JSON을 출력한다.")
    parser.add_argument("video", help="분석할 영상 파일 경로")
    parser.add_argument("--url", default=None, help="원본 URL(있으면 출처에 기록)")
    parser.add_argument("--out", default=None, help="JSON 저장 경로(미지정 시 stdout)")
    parser.add_argument(
        "--no-gemini",
        action="store_true",
        help="비정형 계층(Gemini) 건너뛰고 정형 수치만",
    )
    args = parser.parse_args()

    if not Path(args.video).exists():
        print(f"파일 없음: {args.video}", file=sys.stderr)
        return 1

    profile = analyze_video(args.video, url=args.url, use_gemini=not args.no_gemini)
    payload = json.dumps(profile.model_dump(), ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
        print(f"저장: {args.out}", file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
