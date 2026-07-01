"""영상 백엔드 인터페이스. 패널 하나를 클립으로 만든다.

스키마 경계 뒤의 어댑터라, Veo/Kling/켄 번스가 같은 시그니처를 공유한다.
"""

from __future__ import annotations

from typing import Protocol


class VideoBackend(Protocol):
    def render_panel(
        self,
        still_path: str,
        duration_sec: float,
        width: int,
        height: int,
        fps: int,
        out_path: str,
        motion: str = "",
        prompt: str = "",
        generate_audio: bool = False,
    ) -> str: ...
