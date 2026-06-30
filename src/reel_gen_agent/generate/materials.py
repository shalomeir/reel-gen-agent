"""ReelProfile + ProductionPlan -> Materials. 워킹 스켈레톤은 켄 번스 + 자막만 만든다.

영상 백엔드/voice/bgm은 Milestone 2에서 같은 인터페이스 뒤에 붙인다.
"""

from __future__ import annotations

from pathlib import Path

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
    for panel in profile.storyboard.panels:
        # 스틸이 없는 패널은 워킹 스켈레톤에서 만들 거리가 없으므로 건너뛴다.
        if not panel.still_image:
            continue
        dur = max(0.5, (panel.t_end or 0.0) - (panel.t_start or 0.0))
        clip = str(panels_dir / f"clip_{panel.index}.mp4")
        backend.render_panel(panel.still_image, dur, m.width, m.height, m.fps, clip)
        clips.append(clip)
        sub = str(panels_dir / f"sub_{panel.index}.png")
        render_subtitle_png(panel.subtitle_text or "", m.width, m.height, sub)
        subs.append(sub)
    return Materials(shot_clips=clips, subtitle_pngs=subs)
