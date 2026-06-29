"""생성 파이프라인의 안정 인터페이스(스키마).

각 스테이지가 주고받는 JSON 계약을 pydantic으로 정의한다. 생성 백엔드(이미지·영상
모델)가 바뀌어도 이 스키마는 유지되어 스테이지 간 결합을 끊는다.

흐름: generation_input -> (asset bible) -> storyboard -> video
스키마 구현은 분석 계층의 VideoProfile과 정렬한다(같은 톤/컷/자막/음악 어휘).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- Stage B 출력: 생성 입력 ---------------------------------------------------


class InputMeta(BaseModel):
    duration_sec: float = 15.0
    aspect_ratio: str = "9:16"
    fps: int = 30
    platform: str = "tiktok"  # tiktok / reels / shorts
    language: str = "en"


class ProductSpec(BaseModel):
    name: str
    usp: str | None = None  # 가장 어필할 한 줄
    spec: str | None = None  # 크기/제형/구성 등
    packaging_desc: str | None = None  # 패키지 외형 묘사


class ModelSpec(BaseModel):
    name: str | None = None
    age: str | None = None  # 예: "mid-20s"
    gender: str | None = None
    look: str | None = None  # 외모/분위기
    body: str | None = None  # 체형
    wardrobe: str | None = None  # 착장


class StyleSpec(BaseModel):
    tone: list[str] = Field(default_factory=list)
    pacing: str | None = None  # fast / medium / slow
    cut_mode: str | None = None  # fast_montage / slow_demo / mixed
    palette: list[str] = Field(default_factory=list)
    realism: str = "hyper_realistic"


class VoiceSpec(BaseModel):
    enabled: bool = False  # 기본 off(music_bed), 옵션 데모에서만 on
    type: str | None = None
    accent: str | None = None


class MusicSpec(BaseModel):
    mood: str | None = None
    dynamics: str | None = None  # flat / build


class SubtitleSpec(BaseModel):
    style: str | None = None
    position: str | None = None  # top / center / bottom / mixed
    density: str | None = None  # keyword / full_transcript


class GenerationInput(BaseModel):
    """Stage B 산출물. 컨셉을 생성용 파라미터로 직렬화한 것."""

    meta: InputMeta = Field(default_factory=InputMeta)
    product: ProductSpec
    model: ModelSpec = Field(default_factory=ModelSpec)
    style: StyleSpec = Field(default_factory=StyleSpec)
    voice: VoiceSpec = Field(default_factory=VoiceSpec)
    music: MusicSpec = Field(default_factory=MusicSpec)
    subtitle: SubtitleSpec = Field(default_factory=SubtitleSpec)
    narrative_arc: list[str] = Field(default_factory=list)
    watermark: str | None = None
    # 컷 리듬을 따올 스타일 프로필 경로(분석기 출력). 패널 수/타이밍 시딩에 쓴다.
    style_profile_ref: str | None = None


# --- 에셋 바이블 --------------------------------------------------------------


class CharacterProfile(BaseModel):
    """캐릭터 에셋. 다각도 시트 한 장 + 키샷 한 장으로 일관성을 고정한다."""

    name: str | None = None
    prompt_used: str | None = None
    sheet_image: str | None = None  # 다각도(턴테이블) 한 장
    key_shot_image: str | None = None  # 히어로 클로즈업


class ProductProfile(BaseModel):
    """제품 에셋. 다뷰 시트 한 장 + 히어로샷 한 장."""

    name: str | None = None
    prompt_used: str | None = None
    sheet_image: str | None = None  # 다뷰 한 장
    hero_image: str | None = None


class AssetBible(BaseModel):
    character: CharacterProfile = Field(default_factory=CharacterProfile)
    product: ProductProfile = Field(default_factory=ProductProfile)


# --- 스토리보드 ----------------------------------------------------------------


class StoryboardPanel(BaseModel):
    """한 컷(패널). 비트, 타이밍, 카메라, 잠금 에셋, 자막, 스틸을 담는다."""

    index: int
    beat: str | None = None  # problem / discovery / use / reaction / proof / cta
    t_start: float = 0.0
    t_end: float = 0.0
    shot_type: str | None = None  # wide / medium / macro CU ...
    camera: str | None = None  # handheld / locked-off / push-in ...
    subject_lock: bool = True  # 캐릭터 에셋 참조 여부
    product_lock: bool = False  # 제품 에셋 참조 여부
    prompt: str | None = None  # 패널 스틸 생성 프롬프트
    subtitle_text: str | None = None
    cta_text: str | None = None
    still_image: str | None = None  # 생성된 스틸 경로


class Storyboard(BaseModel):
    """컷 단위 패널 목록. 패널 수/타이밍은 style_profile.cut에서 시딩한다."""

    panels: list[StoryboardPanel] = Field(default_factory=list)
