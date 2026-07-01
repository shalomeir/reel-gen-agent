"""ReelProfile + ProductionPlan -> Materials.

영상은 켄 번스(스켈레톤)/영상 백엔드(Milestone 2)로, 자막은 pilmoji로, BGM은 컷 주기에
bpm을 맞춰 만든다. voice는 voiceover일 때만 별도 생성(on_camera는 영상 모델이 품는다).
실제 Lyria/ElevenLabs는 키가 있을 때 쓰고, 없으면 BGM은 합성 베드로 무음을 피한다.
"""

from __future__ import annotations

from pathlib import Path

from .audio import bpm_for_cuts, synth_music_bed
from .backends.ken_burns import KenBurnsBackend
from .schema import Materials, ProductionPlan, ReelProfile
from .subtitles import render_subtitle_png


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
        # 컷 주기로 목표 bpm을 잡아 BGM에 정렬한다(키 없으면 합성 베드로 대체).
        bpm = bpm_for_cuts(profile.storyboard.panels)
        bgm_audio = synth_music_bed(total_dur, bpm, str(panels_dir / "bgm.wav"))

    return Materials(shot_clips=clips, subtitle_pngs=subs, bgm_audio=bgm_audio)
