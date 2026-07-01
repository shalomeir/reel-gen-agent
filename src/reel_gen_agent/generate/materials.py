"""ReelProfile + ProductionPlan -> Materials.

영상은 켄 번스(스켈레톤)/영상 백엔드(Milestone 2)로, 자막은 pilmoji로, BGM은 컷 주기에
bpm을 맞춰 만든다. voice는 voiceover일 때만 별도 생성(on_camera는 영상 모델이 품는다).
실제 Lyria/ElevenLabs는 키가 있을 때 쓰고, 없으면 BGM은 합성 베드로 무음을 피한다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .audio import bpm_for_cuts, compose_aligned_narration, synth_music_bed
from .backends.ken_burns import DEFAULT_MOTION, KenBurnsBackend
from .schema import Materials, ProductionPlan, ReelProfile
from .subtitles import render_subtitle_png


def _music_bpm(tempo: str | None) -> int | None:
    """MusicSpec.tempo 문자열("136 bpm")에서 bpm 정수를 뽑는다. 없으면 None."""
    if not tempo:
        return None
    m = re.search(r"(\d{2,3})", tempo)
    return int(m.group(1)) if m else None


def build_materials(profile: ReelProfile, plan: ProductionPlan, out_dir: str) -> Materials:
    panels_dir = Path(out_dir) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    m = profile.meta
    backend = KenBurnsBackend()
    clips: list[str] = []
    subs: list[str] = []
    total_dur = 0.0
    for i, panel in enumerate(profile.storyboard.panels):
        # 스틸이 없는 패널은 워킹 스켈레톤에서 만들 거리가 없으므로 건너뛴다.
        if not panel.still_image:
            continue
        dur = max(0.5, (panel.t_end or 0.0) - (panel.t_start or 0.0))
        clip = str(panels_dir / f"clip_{panel.index}.mp4")
        # plan.panel_motions는 패널 순서대로라 위치 i로 맞춘다(없으면 기본 모션).
        motion = plan.panel_motions[i] if i < len(plan.panel_motions) else DEFAULT_MOTION
        backend.render_panel(panel.still_image, dur, m.width, m.height, m.fps, clip, motion=motion)
        clips.append(clip)
        total_dur += dur
        sub = str(panels_dir / f"sub_{panel.index}.png")
        render_subtitle_png(panel.subtitle_text or "", m.width, m.height, sub)
        subs.append(sub)

    bgm_audio: str | None = None
    if plan.bgm != "none" and total_dur > 0:
        # BGM bpm: MusicSpec.tempo(예: 레퍼런스 "136 bpm")가 있으면 우선, 없으면 컷 주기로 산정.
        bpm = _music_bpm(profile.music.tempo) or bpm_for_cuts(profile.storyboard.panels)
        bgm_audio = synth_music_bed(total_dur, bpm, str(panels_dir / "bgm.wav"))

    # voice: 나레이션(voiceover)이면 비트별 대사를 각 패널 t_start에 정렬 배치해 합성한다.
    voice_audio = _build_voice(profile, str(panels_dir), total_dur)

    return Materials(
        shot_clips=clips, subtitle_pngs=subs, bgm_audio=bgm_audio, voice_audio=voice_audio
    )


def _tts_client(desc: str):
    """(text, out) -> path 콜러블. 호출마다 1차 ElevenLabs, 실패/무키면 Gemini TTS 폴백."""
    eleven = None
    if os.environ.get("ELEVENLABS_API_KEY"):
        try:
            from .backends.voice_tts import ElevenLabsVoiceClient

            eleven = ElevenLabsVoiceClient()
        except Exception:
            eleven = None

    def tts(text: str, out: str) -> str:
        if eleven is not None:
            try:
                return eleven.synthesize(text, desc, out)
            except Exception:
                pass  # ElevenLabs 실패 -> Gemini TTS 폴백
        from .backends.gemini_tts import GeminiTTSVoiceClient

        return GeminiTTSVoiceClient().synthesize(text, desc, out)

    return tts


def _build_voice(profile: ReelProfile, panels_dir: str, total_dur: float) -> str | None:
    """비트별 나레이션을 스토리보드 t_start에 맞춰 깔아 전체 길이 voice 트랙으로 만든다.

    delivery가 voiceover이고 대사가 있을 때만. 각 대사를 TTS(1차 ElevenLabs, 폴백 Gemini)한 뒤
    compose_aligned_narration이 패널 t_start에 배치·합성한다. 잘리지 않고 콘티에 맞물린다.
    """
    if profile.narration.delivery != "voiceover":
        return None
    lines = [line for line in profile.narration.lines if line.text.strip()]
    if not lines or total_dur <= 0:
        return None
    try:
        tts = _tts_client(profile.narration.voice.type or "")
        return compose_aligned_narration(
            lines,
            profile.storyboard.panels,
            total_dur,
            tts,
            panels_dir,
            str(Path(panels_dir) / "voice.wav"),
        )
    except Exception:
        return None
