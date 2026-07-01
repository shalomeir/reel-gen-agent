"""ReelProfile + ProductionPlan -> Materials.

영상은 켄 번스(스켈레톤)/영상 백엔드(Milestone 2)로, 자막은 pilmoji로, BGM은 컷 주기에
bpm을 맞춰 만든다. voice는 voiceover일 때만 별도 생성(on_camera는 영상 모델이 품는다).
실제 Lyria/ElevenLabs는 키가 있을 때 쓰고, 없으면 BGM은 합성 베드로 무음을 피한다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .audio import bpm_for_cuts, synth_music_bed
from .backends.ken_burns import KenBurnsBackend
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
    for panel in profile.storyboard.panels:
        # 스틸이 없는 패널은 워킹 스켈레톤에서 만들 거리가 없으므로 건너뛴다.
        if not panel.still_image:
            continue
        dur = max(0.5, (panel.t_end or 0.0) - (panel.t_start or 0.0))
        clip = str(panels_dir / f"clip_{panel.index}.mp4")
        backend.render_panel(panel.still_image, dur, m.width, m.height, m.fps, clip)
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

    # voice: 나레이션(voiceover)이면 대사 스크립트를 ElevenLabs로 TTS해 붙인다(키 있을 때).
    voice_audio = _build_voice(profile, str(panels_dir))

    return Materials(
        shot_clips=clips, subtitle_pngs=subs, bgm_audio=bgm_audio, voice_audio=voice_audio
    )


def _build_voice(profile: ReelProfile, panels_dir: str) -> str | None:
    """voiceover 나레이션 오디오를 만든다. delivery가 voiceover이고 대사·키가 있을 때만."""
    if profile.narration.delivery != "voiceover":
        return None
    text = " ".join(line.text for line in profile.narration.lines if line.text).strip()
    if not text or not os.environ.get("ELEVENLABS_API_KEY"):
        return None
    try:
        from .backends.voice_tts import ElevenLabsVoiceClient

        desc = profile.narration.voice.type or ""
        return ElevenLabsVoiceClient().synthesize(text, desc, str(Path(panels_dir) / "voice.mp3"))
    except Exception:
        return None
