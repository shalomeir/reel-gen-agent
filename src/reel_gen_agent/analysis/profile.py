"""VideoProfile 스키마.

레퍼런스 분석, URL 큐레이션, 생성물 Gate 세 군데가 공유하는 단일 인터페이스.
정형 계층(로컬 라이브러리)과 비정형 계층(Gemini)이 같은 모델에 값을 채운다.
Gemini 구조화 출력 스키마로도 (비정형 일부 모델만) 그대로 재사용한다.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Container(BaseModel):
    """컨테이너 규격. ffprobe로 채운다."""

    aspect_ratio: Optional[str] = None
    fps: Optional[float] = None
    duration_sec: Optional[float] = None
    resolution: Optional[str] = None


class Cut(BaseModel):
    """컷 분포. PySceneDetect로 채운다."""

    count: int = 0
    mean_sec: Optional[float] = None
    min_sec: Optional[float] = None
    max_sec: Optional[float] = None
    # fast_montage(빠른 컷) / slow_demo(느린 시연) / mixed
    mode: Optional[str] = None
    # meaning_based(의미 기반) / beat_based(비트 동기)
    sync: Optional[str] = None
    timestamps: List[float] = Field(default_factory=list)


class Visual(BaseModel):
    """색·밝기 정형 수치(OpenCV) + 모션/느낌 묘사(Gemini)."""

    palette: List[str] = Field(default_factory=list)
    brightness: Optional[float] = None  # 0~255 평균 명도
    contrast: Optional[float] = None  # 명도 표준편차
    motion: Optional[str] = None  # Gemini 묘사: still / gentle / dynamic


class Subtitle(BaseModel):
    """자막 스타일. Gemini가 텍스트와 스타일을 함께 묘사한다."""

    text: List[str] = Field(default_factory=list)
    font_style: Optional[str] = None  # 예: bold sans-serif
    color: Optional[str] = None
    position: Optional[str] = None  # top / center / bottom / mixed
    density: Optional[str] = None  # keyword / full_transcript
    emoji: List[str] = Field(default_factory=list)


class Voice(BaseModel):
    """보이스(나레이션/대사). 없으면 present=False."""

    present: bool = False
    tone: Optional[str] = None  # 목소리 톤 묘사
    pace: Optional[str] = None  # slow / medium / fast


class Music(BaseModel):
    """음악. continuous/bpm은 librosa, beat_synced/dynamics는 librosa+Gemini 합의."""

    continuous: Optional[bool] = None
    beat_synced: Optional[bool] = None
    dynamics: Optional[str] = None  # flat / build
    bpm: Optional[float] = None
    intro_silence_sec: Optional[float] = None


class Hook(BaseModel):
    """0~3초 후크. Gemini가 채운다."""

    headline: Optional[str] = None
    product_line: Optional[str] = None
    bottom_caption: Optional[str] = None
    visual: Optional[str] = None  # 비주얼 훅 묘사
    window_sec: List[float] = Field(default_factory=lambda: [0.0, 3.0])


class Source(BaseModel):
    """출처 추적."""

    path: Optional[str] = None
    url: Optional[str] = None
    extractor_id: Optional[str] = None


class VideoProfile(BaseModel):
    """영상 한 편의 통합 프로필."""

    container: Container = Field(default_factory=Container)
    cut: Cut = Field(default_factory=Cut)
    visual: Visual = Field(default_factory=Visual)
    subtitle: Subtitle = Field(default_factory=Subtitle)
    voice: Voice = Field(default_factory=Voice)
    music: Music = Field(default_factory=Music)
    hook: Hook = Field(default_factory=Hook)
    tone: List[str] = Field(default_factory=list)
    narrative_arc: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    source: Source = Field(default_factory=Source)


class GeminiDescription(BaseModel):
    """Gemini 구조화 출력 전용 서브셋(비정형 필드만).

    analyze_video가 이 결과를 VideoProfile에 병합한다. 정형 필드(container/cut 등)는
    로컬 계층이 채우므로 여기 포함하지 않는다.
    """

    visual_palette: List[str] = Field(default_factory=list)
    visual_motion: Optional[str] = None
    subtitle: Subtitle = Field(default_factory=Subtitle)
    voice: Voice = Field(default_factory=Voice)
    music_dynamics: Optional[str] = None  # flat / build
    music_beat_synced: Optional[bool] = None
    hook: Hook = Field(default_factory=Hook)
    tone: List[str] = Field(default_factory=list)
    narrative_arc: List[str] = Field(default_factory=list)
    description: Optional[str] = None
