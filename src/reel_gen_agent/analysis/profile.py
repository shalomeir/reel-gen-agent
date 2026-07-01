"""VideoProfile 스키마.

레퍼런스 분석, URL 큐레이션, 생성물 Gate 세 군데가 공유하는 단일 인터페이스.
정형 계층(로컬 라이브러리)과 비정형 계층(Gemini)이 같은 모델에 값을 채운다.
Gemini 구조화 출력 스키마로도 (비정형 일부 모델만) 그대로 재사용한다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Container(BaseModel):
    """컨테이너 규격. ffprobe로 채운다."""

    aspect_ratio: str | None = None
    fps: float | None = None
    duration_sec: float | None = None
    resolution: str | None = None


class Cut(BaseModel):
    """컷 분포. PySceneDetect로 채운다."""

    count: int = 0
    mean_sec: float | None = None
    min_sec: float | None = None
    max_sec: float | None = None
    # fast_montage(빠른 컷) / slow_demo(느린 시연) / mixed
    mode: str | None = None
    # meaning_based(의미 기반) / beat_based(비트 동기)
    sync: str | None = None
    timestamps: list[float] = Field(default_factory=list)


class Visual(BaseModel):
    """색·밝기 정형 수치(OpenCV) + 모션/느낌 묘사(Gemini)."""

    palette: list[str] = Field(default_factory=list)
    brightness: float | None = None  # 0~255 평균 명도
    contrast: float | None = None  # 명도 표준편차
    motion: str | None = None  # Gemini 묘사: still / gentle / dynamic


class Subtitle(BaseModel):
    """자막 스타일. Gemini가 텍스트와 스타일을 함께 묘사한다."""

    text: list[str] = Field(default_factory=list)
    font_style: str | None = None  # 예: bold sans-serif
    color: str | None = None
    position: str | None = None  # top / center / bottom / mixed
    density: str | None = None  # keyword / full_transcript
    emoji: list[str] = Field(default_factory=list)


class Voice(BaseModel):
    """보이스(나레이션/대사). 없으면 present=False."""

    present: bool = False
    # 화면 속 인물이 카메라를 보고 직접 말하는가(입 움직임=발화). True면 생성 시 온카메라
    # 립싱크(영상 모델 네이티브 음성) 경로로 재현하고, False면 화면 밖 나레이션(voiceover)로 본다.
    on_camera: bool = False
    tone: str | None = None  # 목소리 톤 묘사
    pace: str | None = None  # slow / medium / fast


class Music(BaseModel):
    """음악. continuous/bpm은 librosa, beat_synced/dynamics는 librosa+Gemini 합의."""

    continuous: bool | None = None
    beat_synced: bool | None = None
    dynamics: str | None = None  # flat / build
    bpm: float | None = None
    intro_silence_sec: float | None = None


class Hook(BaseModel):
    """0~3초 후크. Gemini가 채운다."""

    headline: str | None = None
    product_line: str | None = None
    bottom_caption: str | None = None
    visual: str | None = None  # 비주얼 훅 묘사
    window_sec: list[float] = Field(default_factory=lambda: [0.0, 3.0])


class Subject(BaseModel):
    """화면에 나오는 인물(모델/크리에이터) 묘사. 생성 시 캐릭터 시딩에 쓴다.

    없으면 present=False. 있으면 성별·나이대·인종·피부톤·헤어·착장까지 최대한 잡아, 생성
    캐릭터가 레퍼런스 인물을 따르도록 한다(입력 레퍼런스 반영). 특히 인종과 피부톤은
    캐릭터 정체성을 좌우하므로 관측된 대로 명확히 남긴다. Gemini가 채운다.
    """

    present: bool = False
    gender: str | None = None  # female / male / group
    age_range: str | None = None  # 예: "early 20s"
    ethnicity: str | None = None  # 예: "black/african", "east asian", "white" (관측된 대로)
    skin_tone: str | None = None  # 예: "deep", "medium tan", "fair" (인종 판단을 구체 관측으로 보강)
    hair: str | None = None  # 길이·색·스타일(예: "long dark curly")
    look: str | None = None  # 외모/분위기 한 줄
    wardrobe: str | None = None  # 착장


class Product(BaseModel):
    """화면에 나오는 제품 묘사. 생성 시 제품 시딩 참고에 쓴다. 없으면 present=False.

    브랜드·제품명을 복제하려는 게 아니라(생성물은 사용자 제품을 쓴다), 카테고리·제형·
    용기·색 같은 시각 특성을 잡아 생성 제품이 레퍼런스 결과 유형을 따르게 한다. Gemini가 채운다.
    """

    present: bool = False
    category: str | None = None  # 예: "serum mist", "cushion foundation"
    form: str | None = None  # 제형/형태(예: "jelly-to-mist", "cream", "stick")
    packaging: str | None = None  # 용기 형태(예: "frosted spray bottle")
    colors: list[str] = Field(default_factory=list)  # 제품/패키지 주요 색
    text_visible: list[str] = Field(default_factory=list)  # 패키지에 읽히는 텍스트(관측된 대로)


class Source(BaseModel):
    """출처 추적."""

    path: str | None = None
    url: str | None = None
    extractor_id: str | None = None


class VideoProfile(BaseModel):
    """영상 한 편의 통합 프로필."""

    container: Container = Field(default_factory=Container)
    cut: Cut = Field(default_factory=Cut)
    visual: Visual = Field(default_factory=Visual)
    subtitle: Subtitle = Field(default_factory=Subtitle)
    voice: Voice = Field(default_factory=Voice)
    music: Music = Field(default_factory=Music)
    hook: Hook = Field(default_factory=Hook)
    subject: Subject = Field(default_factory=Subject)
    product: Product = Field(default_factory=Product)
    tone: list[str] = Field(default_factory=list)
    narrative_arc: list[str] = Field(default_factory=list)
    description: str | None = None
    source: Source = Field(default_factory=Source)


class GeminiDescription(BaseModel):
    """Gemini 구조화 출력 전용 서브셋(비정형 필드만).

    analyze_video가 이 결과를 VideoProfile에 병합한다. 정형 필드(container/cut 등)는
    로컬 계층이 채우므로 여기 포함하지 않는다.
    """

    visual_palette: list[str] = Field(default_factory=list)
    visual_motion: str | None = None
    subtitle: Subtitle = Field(default_factory=Subtitle)
    voice: Voice = Field(default_factory=Voice)
    music_dynamics: str | None = None  # flat / build
    music_beat_synced: bool | None = None
    hook: Hook = Field(default_factory=Hook)
    subject: Subject = Field(default_factory=Subject)
    product: Product = Field(default_factory=Product)
    tone: list[str] = Field(default_factory=list)
    narrative_arc: list[str] = Field(default_factory=list)
    description: str | None = None
