"""생성 파이프라인의 안정 인터페이스(스키마).

각 스테이지가 주고받는 JSON 계약을 pydantic으로 정의한다. 생성 백엔드(이미지·영상
모델)가 바뀌어도 이 스키마는 유지되어 스테이지 간 결합을 끊는다([ADR.md] ADR-0003).

두 페이즈는 스키마로만 통신한다:
  plan(Planning)      입력 -> ReelProfile
  execute(Production)  ReelProfile -> 영상 + RunManifest + 산출물

계약 정본은 specs/information-schema.md, 흐름은 specs/workflows.md, 후크 계약은
specs/hook-generator.md다. 코드와 spec이 어긋나면 spec이 이긴다.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

# --- 영상 포맷 메타 -----------------------------------------------------------

# 영상 포맷 기본값과 가드레일은 specs/trd.md "영상 포맷 기본값과 가드레일"이 정본이다.
# 기본값은 필드 디폴트로, 가드레일은 아래 밸리데이터로 강제한다. 코드와 스펙이
# 어긋나면 스펙이 이긴다.
MAX_DURATION_SEC = 60.0  # 하드 상한: 아주 길어도 60초를 넘지 않는다
MIN_DURATION_SEC = 1.0
ALLOWED_FPS = {
    24,
    25,
    30,
    50,
    60,
}  # 표준 프레임레이트. 백엔드가 24만 내는 경우도 있어 30 강제 안 함
MAX_WIDTH = 1080  # 1080p가 상한. 업스케일 금지(더 낮은 해상도만 허용)
MAX_HEIGHT = 1920
REQUIRED_ASPECT_RATIO = "9:16"


class InputMeta(BaseModel):
    """영상 포맷 메타. 별다른 사유가 없으면 기본값으로 만든다.

    목적·후크·컨셉이 명시하면 가드레일 안에서 조정할 수 있다. 검증은 specs/trd.md의
    포맷 계약을 따른다.
    """

    duration_sec: float = 14.0  # 기본 제작 포맷 14초(7초 멀티샷 2개). 1~60초 범위, 60초 초과 거부
    aspect_ratio: str = REQUIRED_ASPECT_RATIO  # 9:16 고정
    width: int = 1080  # 1080x1920(1080p) 기본·상한
    height: int = 1920
    fps: int = 30  # 30 기본. 백엔드 지원 범위에 맞춰 24~60 표준값 허용
    platform: str = "tiktok"  # tiktok / reels / shorts
    language: str = "en"

    @field_validator("duration_sec")
    @classmethod
    def _check_duration(cls, v: float) -> float:
        if not (MIN_DURATION_SEC <= v <= MAX_DURATION_SEC):
            raise ValueError(
                f"duration_sec must be {MIN_DURATION_SEC}~{MAX_DURATION_SEC}s "
                f"(60초 초과 거부), got {v}"
            )
        return v

    @field_validator("fps")
    @classmethod
    def _check_fps(cls, v: int) -> int:
        if v not in ALLOWED_FPS:
            raise ValueError(f"fps must be one of {sorted(ALLOWED_FPS)}, got {v}")
        return v

    @field_validator("aspect_ratio")
    @classmethod
    def _check_aspect_ratio(cls, v: str) -> str:
        if v != REQUIRED_ASPECT_RATIO:
            raise ValueError(f"aspect_ratio must be {REQUIRED_ASPECT_RATIO}, got {v}")
        return v

    @model_validator(mode="after")
    def _check_resolution(self) -> InputMeta:
        # 1080p 상한, 업스케일 금지. 더 낮은 해상도는 사유가 있을 때만 허용한다.
        if self.width > MAX_WIDTH or self.height > MAX_HEIGHT:
            raise ValueError(
                f"resolution must not exceed {MAX_WIDTH}x{MAX_HEIGHT} (업스케일 금지), "
                f"got {self.width}x{self.height}"
            )
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width/height must be positive")
        # 9:16 비율 유지: width*16 == height*9
        if self.width * 16 != self.height * 9:
            raise ValueError(f"resolution must keep 9:16 ratio, got {self.width}x{self.height}")
        return self

    @property
    def resolution(self) -> str:
        """컨테이너 표기와 같은 'WxH' 문자열."""
        return f"{self.width}x{self.height}"


# --- 제품·캐릭터·스타일 기본 스펙 ---------------------------------------------


class ProductSpec(BaseModel):
    name: str
    usp: str | None = None  # 가장 어필할 한 줄
    spec: str | None = None  # 크기/제형/구성 등
    packaging_desc: str | None = None  # 패키지 외형 묘사
    # 제품 시각 정체성. 컷마다 제품이 흔들리지 않게 이 값들을 모든 생성 단계(히어로 이미지·컷
    # 스틸·영상 프롬프트)에 일관 주입한다. 브랜드/라벨은 복제하지 않되(text_visible 제외) 카테고리·
    # 제형·용기·색 같은 형태 정체성은 레퍼런스와 거의 같게 잡는다(사용자 지시: 브랜드만 다르게).
    category: str | None = None  # 예: "glow serum", "cushion foundation"
    form: str | None = None  # 제형/질감(예: "lightweight jelly-to-mist", "cream")
    colors: list[str] = Field(default_factory=list)  # 제품/패키지 주요 색
    key_features: list[str] = Field(default_factory=list)  # 식별 특징(펌프/드로퍼/프로스티드 등)
    # product_analysis 노드가 뽑은 가능 행동 목록. 스토리보드가 사용 장면에 끌어 쓴다.
    affordances: list[str] = Field(default_factory=list)


class ModelSpec(BaseModel):
    """캐릭터 설정. voice도 이 설정에서 음색을 유도한다([ADR.md] ADR-0012)."""

    name: str | None = None
    age: str | None = None  # 예: "mid-20s"
    gender: str | None = None
    look: str | None = None  # 외모/분위기
    body: str | None = None  # 체형
    wardrobe: str | None = None  # 착장


class StyleSpec(BaseModel):
    """레거시 스타일 스펙(GenerationInput용). ReelProfile은 StyleDimensions를 쓴다."""

    tone: list[str] = Field(default_factory=list)
    pacing: str | None = None  # fast / medium / slow
    cut_mode: str | None = None  # fast_montage / slow_demo / mixed
    palette: list[str] = Field(default_factory=list)
    realism: str = "hyper_realistic"


class VoiceSpec(BaseModel):
    """voice 음색 속성. 캐릭터(ModelSpec)에서 유도한다. on/off는 NarrationSpec.delivery.

    tone/pace는 발화의 '결'이다. 레퍼런스가 있으면 그 관측된 전달 방식(예: whispered soft,
    slow)을 실어 TTS 연기와 대사 톤을 맞춘다. 없으면 None(캐릭터 페르소나 기본 연기).
    """

    enabled: bool = True  # voice 되도록 사용. 실제 on/off는 delivery가 governs
    type: str | None = None  # 음색/딕션(캐릭터 페르소나)
    accent: str | None = None
    tone: str | None = None  # 전달 톤(예: "calm, whispered, soft") - 레퍼런스 시딩
    pace: str | None = None  # slow / medium / fast - 레퍼런스 시딩
    from_character: bool = True  # ModelSpec에서 유도했는지


class MusicSpec(BaseModel):
    mood: str | None = None
    dynamics: str | None = None  # flat / build (강약의 개략 플래그)
    # 에너지 컨투어(강약) 세부 서술. 예: "soft intro, subtle lift toward the end, no big drop".
    # Lyria 프롬프트에 그대로 실어 강약을 세밀히 전달한다(coarse dynamics 플래그를 보완).
    dynamics_detail: str | None = None
    style: str | None = None  # 장르/스타일
    type: str | None = None  # 유형(예: lo-fi, upbeat pop)
    # 핵심 악기·사운드 팔레트(예: "punchy 808s, glossy synth plucks, side-chained pads").
    # Lyria 프롬프트 프레임워크가 악기 명시를 요구한다(없으면 장르 기본값으로 밋밋해짐).
    instrumentation: str | None = None
    tempo: str | None = None  # 컷 리듬 정렬 템포
    # BGM 존재감(믹스 의도). 나레이션이 정보 전달이면 "background", 바이브 중심이고 나레이션이
    # 감탄사·최소면 "prominent"(발화 아래에서도 더 크게). 음악 노드(LLM)가 정하고 execute가 따른다.
    prominence: str = "background"  # background / prominent
    # 이 컨셉이 음악 베드를 쓸지("bed") 배경음 없이 효과음만("none") 갈지. 음악 노드가 정한다.
    bgm: str = "bed"  # bed / none
    # 프로덕션 효과음(비-diegetic: 컷 전환 whoosh, 그래픽 액센트, 후크 라이저, 엔딩 징글)을
    # 얹을지. 씬 내 자연음(분사·탭)은 영상 모델이 낸다. 예능식 편집 컨셉에서만 켠다(옵션).
    sfx: bool = False
    # 트랙에 보컬/가사가 있는지(있으면 배경으로 너무 묻지 않게 믹스 존재감을 올린다).
    vocal: bool = False


class SubtitleSpec(BaseModel):
    style: str | None = None
    position: str | None = None  # top / center / bottom / mixed
    density: str | None = None  # keyword / full_transcript


class GenerationInput(BaseModel):
    """레거시 Stage B 산출물. 워킹 스켈레톤의 손작성 입력 경로용.

    ReelProfile 도입 후에는 ReelProfile의 부분집합에 해당한다. 기획 페이즈가 완성되면
    ReelProfile로 수렴한다(specs/information-schema.md 3번 9).
    """

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


# --- 후크 (계약 정본: specs/hook-generator.md) --------------------------------

# 후크 유형 표(코드 -> 키, 라벨, 제품 적합도). 하드코딩 금지: 코드는 이 데이터를 읽는다.
HOOK_TYPES: dict[str, dict[str, str]] = {
    "H1": {"key": "before_after", "label": "비포/애프터·시간경과 증명", "product_fit": "very_high"},
    "H2": {"key": "problem_solution", "label": "문제 제기 -> 해결 약속", "product_fit": "high"},
    "H3": {"key": "secret_knowhow", "label": "호기심·비밀·노하우", "product_fit": "high"},
    "H4": {"key": "experiment_proof", "label": "실험·증명(데모, A/B)", "product_fit": "high"},
    "H5": {"key": "reversal", "label": "반전·역설·충격", "product_fit": "medium"},
    "H6": {"key": "number_limit", "label": "숫자·제한(시간·단계)", "product_fit": "high"},
    "H7": {"key": "pov_immersion", "label": "POV·상황 몰입", "product_fit": "medium_high"},
    "H8": {"key": "confession_relatable", "label": "개인 고백·공감", "product_fit": "medium"},
    "H9": {"key": "authority_proof", "label": "권위·사회적 증거", "product_fit": "high"},
    "H10": {"key": "product_reveal", "label": "신제품 소개·리빌", "product_fit": "very_high"},
    "H11": {"key": "routine_framing", "label": "루틴 선언", "product_fit": "high"},
    "H12": {"key": "choice_challenge", "label": "양자택일·챌린지", "product_fit": "low"},
}

# 카테고리 -> 기본 후보 유형. 상수가 아니라 설정 테이블(새 카테고리는 행 추가).
CATEGORY_HOOK_DEFAULTS: dict[str, list[str]] = {
    "skincare_efficacy": ["H1", "H9", "H2"],
    "launch": ["H10", "H3"],
    "routine": ["H11", "H6"],
    "info": ["H3", "H6"],
    "demo": ["H4", "H1"],
    "lifestyle": ["H7", "H12"],
}


class HookRequest(BaseModel):
    """후크 생성 입력. GenerationInput/ReelProfile에서 파생한다."""

    product: ProductSpec
    category: str | None = None  # CATEGORY_HOOK_DEFAULTS 키. 없으면 추론
    tone: list[str] = Field(default_factory=list)
    character: str = ""  # 등장 캐릭터 요약(주인공 문맥). 후크 문구·톤이 캐릭터에 맞도록.
    platform: str = "tiktok"
    language: str = "en"
    duration_sec: float = 18.0
    count: int = 3  # 생성할 후보 수
    forced_type: str | None = None  # H1~H12 강제. 없으면 카테고리 기본에서 선택
    style_profile_ref: str | None = None


class HookCandidate(BaseModel):
    """후크 후보 하나. 텍스트·비주얼·오프닝 비트·본문 연결을 한 묶음으로."""

    hook_type: str  # H1~H12 코드
    headline: str | None = None  # 상단 텍스트. no_text_visual이면 None 가능
    bottom_caption: str | None = None  # 하단 텍스트
    reinforce_overlap: bool = False  # 상/하단 같은 문구 겹쳐 박기
    no_text_visual: bool = False  # 텍스트 없이 비주얼·사운드만
    visual_direction: str = ""  # 0초 비주얼 지시문
    opening_beat: str = ""  # narrative_arc 첫 비트
    bridge: str = ""  # 후크 -> 본문 연결(제품·결과 핵심 장면)
    window_sec: tuple[float, float] = (0.0, 3.0)  # 후크 노출 구간
    variant: str | None = None  # "question" / "command"
    rationale: str = ""  # 왜 먹히는지 한 문장

    @field_validator("hook_type")
    @classmethod
    def _check_hook_type(cls, v: str) -> str:
        if v not in HOOK_TYPES:
            raise ValueError(f"hook_type must be one of {sorted(HOOK_TYPES)}, got {v}")
        return v


class HookSet(BaseModel):
    candidates: list[HookCandidate] = Field(default_factory=list)
    request: HookRequest | None = None  # 입력 에코(재현용)
    selected: int | None = None  # 게이트에서 고른 후보 인덱스


# --- 다섯 스타일 차원 (ReelProfile용) -----------------------------------------


class CutRhythm(BaseModel):
    basis: str = "semantic_action"  # semantic_action / beat_sync
    pattern: str | None = None  # 예: 빠른 컷 구간과 롱홀드가 클러스터로 교차
    source: str = "llm"  # reference(style_profile.cut 시딩) / llm


class StyleDimensions(BaseModel):
    """다섯 스타일 차원. concept 노드가 채운다(레퍼런스 있으면 분석, 없으면 LLM).

    hook은 별도 hook 노드의 HookSet에서 채택한 후보를 가리킨다(specs/hook-generator.md).
    """

    tone: list[str] = Field(default_factory=list)
    pacing: str | None = None  # fast_montage / slow_demo / mixed (컷 빈도/성격)
    # 샷 내부 모션 강도(still/gentle/dynamic). 컷 빈도(pacing)와 별개 축이다. 빠른 컷이라도
    # 샷 안은 부드러울 수 있다(레퍼런스1: 빠른 컷 + gentle 모션). 레퍼런스 visual.motion에서 시딩.
    motion: str | None = None  # still / gentle / dynamic
    cut_rhythm: CutRhythm = Field(default_factory=CutRhythm)
    hook: HookCandidate | None = None  # 채택된 후크
    subtitle: SubtitleSpec = Field(default_factory=SubtitleSpec)
    palette: list[str] = Field(default_factory=list)
    realism: str = "hyper_realistic"


# --- 에셋 바이블 (캐릭터/제품/환경) -------------------------------------------


class AssetView(BaseModel):
    """필수 뷰 체크리스트 항목. 게이트가 satisfied로 충족을 검증한다."""

    name: str  # 예: face_closeup / front / special_function
    required: bool = True
    image: str | None = None  # 이 뷰의 이미지 경로(개별 컷일 때)
    satisfied: bool = False  # 시트나 개별 컷이 이 뷰를 충족하는지


class CharacterProfile(BaseModel):
    """캐릭터 에셋. 멀티뷰 시트 한 장 + 필수 뷰 체크리스트."""

    name: str | None = None
    prompt_used: str | None = None
    sheet_image: str | None = None  # 다각도(턴테이블) 한 장
    key_shot_image: str | None = None  # 히어로 클로즈업
    # 필수 뷰: 얼굴 클로즈업, 표정 변화, 전신, 좌/우 얼굴
    views: list[AssetView] = Field(default_factory=list)


class ProductProfile(BaseModel):
    """제품 에셋. 다뷰 시트 + 히어로샷 + 필수 뷰 체크리스트."""

    name: str | None = None
    prompt_used: str | None = None
    sheet_image: str | None = None
    hero_image: str | None = None
    # 필수 뷰: 정면, 좌우/위, 박스 안, 특수 기능
    views: list[AssetView] = Field(default_factory=list)


class EnvironmentSpec(BaseModel):
    """배경·촬영 환경. 텍스트 정의는 항상, 이미지는 needs_image일 때만."""

    location: str | None = None
    setting: str | None = None
    lighting: str | None = None
    time_of_day: str | None = None
    mood: str | None = None
    props: list[str] = Field(default_factory=list)
    needs_image: bool = False
    reference_image: str | None = None


class AssetBible(BaseModel):
    character: CharacterProfile = Field(default_factory=CharacterProfile)
    product: ProductProfile = Field(default_factory=ProductProfile)
    environment: EnvironmentSpec = Field(default_factory=EnvironmentSpec)
    # 대표 키 비주얼(상대 파일명). plan 확정 시 캐릭터·제품·환경 에셋 + 프로필을 합쳐 만든
    # "이 영상이 어떤 느낌인지" 한 장. 커버로도, 중간 세그먼트 앵커 스틸로도 재활용 가능.
    key_visual: str | None = None


# --- 스토리보드 ----------------------------------------------------------------


class StoryboardPanel(BaseModel):
    """한 컷(패널). 비트, 타이밍, 카메라, 잠금 에셋, 자막, 스틸을 담는다."""

    index: int
    beat: str | None = None  # hook / problem / discovery / use / reaction / proof / cta
    t_start: float = 0.0
    t_end: float = 0.0
    shot_type: str | None = None  # wide / medium / macro CU ...
    camera: str | None = None  # handheld / locked-off / push-in ...
    # 이 컷의 의미 있는 행동/사건(스토리 전개). "카메라 보고 포즈"가 아니라 서사를 진전시키는
    # 동작·상호작용·효과. 스토리보드 노드(LLM)가 채우고, execute의 영상 프롬프트가 그대로 쓴다.
    action: str | None = None
    subject_lock: bool = True  # 캐릭터 에셋 참조 여부
    product_lock: bool = False  # 제품 에셋 참조 여부
    environment_lock: bool = True  # 환경 에셋 참조 여부
    prompt: str | None = None  # 패널 스틸 생성 프롬프트
    subtitle_text: str | None = None
    # 이 컷의 프로덕션 효과음 큐(비-diegetic 편집 효과: 전환 whoosh, sparkle, 후크 라이저,
    # 엔딩 징글). 씬 내 자연음이 아니다(그건 영상 모델 몫). 없으면 None. 스토리보드가 드물게
    # 채우고, 플랜이 SFX를 켰을 때만 execute가 생성·믹스한다(옵션).
    sfx: str | None = None
    cta_text: str | None = None
    still_image: str | None = None  # 생성된 스틸 경로
    key_image: str | None = None  # 컷별 핵심 스틸(선택)
    renderer: str | None = None  # i2v / ken_burns / canvas (ProductionPlan과 정렬)


class Storyboard(BaseModel):
    """컷 단위 패널 목록. 패널 수/타이밍은 style_profile.cut에서 시딩한다."""

    global_prompt: str | None = None  # 모든 샷에 흐르는 공통 맥락
    panels: list[StoryboardPanel] = Field(default_factory=list)


# --- 기획 입력·대사·출처·생산 의도 --------------------------------------------


class Objective(BaseModel):
    """영상 목적(필수). 없으면 그래프 진입 불가."""

    goal: str
    video_type: str | None = None  # 광고/언박싱/튜토리얼/후기 등
    target_audience: str | None = None
    key_message: str | None = None


class AssetInput(BaseModel):
    """캐릭터/제품 입력. 없으면 의도(absent_reason)를 캡처한다."""

    kind: str  # character / product
    source: str | None = None  # 이미지 경로, URL, 또는 텍스트 묘사
    present: bool = True
    absent_reason: str | None = None  # 없을 때 왜 없는지(의도)


class NarrationLine(BaseModel):
    panel_index: int
    text: str


class NarrationSpec(BaseModel):
    """대사 스크립트 + 전달 방식. voice는 되도록 사용([ADR.md] ADR-0012).

    delivery가 ProductionPlan.voice_strategy로 해소된다
    (on_camera->integrated, voiceover->separate_tts, none->none).
    """

    delivery: str = "voiceover"  # voiceover(나레이션, 기본) / on_camera / none
    lines: list[NarrationLine] = Field(default_factory=list)
    voice: VoiceSpec = Field(default_factory=VoiceSpec)  # 캐릭터에서 유도
    language: str = "en"
    text_model: str | None = None  # 대사 생성에 쓴 LLM(Claude/Gemini)


class Provenance(BaseModel):
    style_source: str = "llm"  # reference / llm
    reference_ref: str | None = None
    seeds: dict = Field(default_factory=dict)
    text_model: str | None = None
    schema_version: str = "1"


class ProductionIntent(BaseModel):
    """이식 가능한 생산 의도. 실제 해소는 ProductionPlan."""

    voice_pref: str = "auto"  # on_camera / voiceover / none / auto. 기본 voice 사용
    multishot_pref: str = "auto"  # prefer / avoid / auto
    key_image_per_cut_pref: str = "auto"  # prefer / avoid / auto
    shot_renderer_pref: str = "auto"  # i2v / ken_burns / canvas / auto
    bgm_pref: str = "gen"  # gen / file / none
    sfx_pref: bool = False


# --- ReelProfile (동결 합본, profile.json) ------------------------------------


class ReelProfile(BaseModel):
    """기획의 동결 합본. plan 산출, execute 입력. 같은 ReelProfile -> 유사 영상.

    파일명은 ReelProfile-{핵심컨셉}-{생성일시}.json(specs/information-schema.md).
    """

    schema_version: str = "1"
    meta: InputMeta = Field(default_factory=InputMeta)
    objective: Objective
    product: ProductSpec
    character: ModelSpec = Field(default_factory=ModelSpec)
    style: StyleDimensions = Field(default_factory=StyleDimensions)
    narrative_arc: list[str] = Field(default_factory=list)
    asset_bible: AssetBible = Field(default_factory=AssetBible)
    storyboard: Storyboard = Field(default_factory=Storyboard)
    narration: NarrationSpec = Field(default_factory=NarrationSpec)
    music: MusicSpec = Field(default_factory=MusicSpec)
    production_intent: ProductionIntent = Field(default_factory=ProductionIntent)
    provenance: Provenance = Field(default_factory=Provenance)
    watermark: str | None = None


# --- 생산 계획·능력·재료 (execute 런타임) -------------------------------------


class ModelCapability(BaseModel):
    """capability matrix 항목. 코드에 모델을 박지 않고 config/.env 데이터로 둔다."""

    model_id: str
    lane: str  # vertex / fal / local
    multishot: bool = False
    integrated_voice: bool = False  # 영상+발화/립싱크 네이티브 지원
    max_clip_sec: float = 8.0
    max_resolution: str = "1080x1920"


class ProductionPlan(BaseModel):
    """ProductionIntent를 가용 리소스·모델 능력에 맞춰 해소한 결과. RunManifest에 기록."""

    video_model: str | None = None
    capability: ModelCapability | None = None
    voice_strategy: str = "none"  # integrated / separate_tts / none
    multishot: bool = False
    key_image_per_cut: bool = False
    panel_renderers: list[str] = Field(default_factory=list)  # 패널별 i2v/ken_burns/canvas
    panel_motions: list[str] = Field(default_factory=list)  # 켄 번스 폴백 패널별 모션(beat 기반)
    # 영상 모델 호출 1회 단위(패널 인덱스 그룹). ken_burns면 패널당 1개, 영상 모델이면
    # max_clip_sec 이하로 묶어 ≤15초는 ≤2회 호출한다([multishot-segments.md]).
    segments: list[list[int]] = Field(default_factory=list)
    bgm: str = "none"  # gen / file / none
    sfx: bool = False
    # 영상 모델이 씬 오디오(효과음/앰비언스)를 함께 생성할지. 기본 True(효과음 때문에 켠다).
    # voiceover면 _speech_directive가 "오디오에 발화·음성 금지, 앰비언스/효과음만"을 명시해 대사가
    # 섞이지 않게 하고, integrated면 그게 발화(립싱크) 트랙이 된다.
    video_native_audio: bool = True
    fallbacks_applied: list[str] = Field(default_factory=list)


class Materials(BaseModel):
    """병렬 재료 노드가 채우고 assemble가 소비."""

    key_images: list[str] = Field(default_factory=list)
    shot_clips: list[str] = Field(default_factory=list)  # concat 순서
    voice_audio: str | None = None
    bgm_audio: str | None = None
    sfx_audio: list[str] = Field(default_factory=list)
    # sfx_audio와 평행한 시작 시각(초). 최종 타임라인에서 각 SFX를 이 지점에 얹는다.
    sfx_starts: list[float] = Field(default_factory=list)
    subtitle_pngs: list[str] = Field(default_factory=list)  # 패널별 자막 PNG(투명)
    # subtitle_pngs와 평행한 [start, end] 초 구간. 최종 타임라인에 시간 기반으로 덮는다.
    subtitle_spans: list[list[float]] = Field(default_factory=list)
    # 클립에 영상 모델 네이티브 음성(온카메라 발화)이 들어 있는가. True면 assemble이 그 오디오를
    # 보존해 BGM과 믹스한다(별도 voice 없음). 기본 나레이션 경로는 False.
    native_audio: bool = False
    # 발화가 있을 때 BGM 볼륨(플랜 music.prominence가 정함). None이면 assemble 기본 덕킹.
    bgm_gain: float | None = None


# --- 실행 매니페스트 (conformance 게이트가 노드/머지 무결성을 검증하는 계약) -----


class NodeRun(BaseModel):
    """그래프 노드 하나의 실행 기록. status와 산출물 경로, 핵심 프롬프트를 남긴다."""

    name: str  # concept / hook / asset_bible / storyboard / video / assembly ...
    status: str = "done"  # done / error / skipped
    artifacts: list[str] = Field(default_factory=list)  # 이 노드가 만든 파일 경로
    prompt: str | None = None  # 외부 모델에 보낸 핵심 프롬프트 원문(키·토큰은 레다크션)
    error: str | None = None


class RunManifest(BaseModel):
    """생성 한 회차의 실행 기록. conformance 게이트가 이걸 읽어 노드/머지 무결성을 본다.

    생성 그래프가 단계마다 NodeRun을 append하고 끝에 final_video와 panel_segments를 채운다.
    """

    run_id: str | None = None  # 간단제목축약-생성일시(폴더명과 동일)
    input_path: str | None = None  # generation_input.json 또는 ReelProfile 경로
    storyboard_path: str | None = None
    final_video: str | None = None
    panel_segments: list[str] = Field(default_factory=list)  # concat 순서대로의 클립 경로
    nodes: list[NodeRun] = Field(default_factory=list)
    production_plan: ProductionPlan | None = None  # 런타임 해소 결과


# --- 최종 산출 리포트 (describe / report 노드) --------------------------------


class OutlineItem(BaseModel):
    timecode: str  # mm:ss
    content: str


class UploadKit(BaseModel):
    """업로드용 자산. describe 노드 산출, upload.md로 렌더."""

    title: str
    outline: list[OutlineItem] = Field(default_factory=list)
    caption: str = ""  # 본문 멘트(컨셉 맞춤, 제품명 포함)
    hashtags: list[str] = Field(default_factory=list)


class BgmReport(BaseModel):
    kind: str = "none"  # gen / file / none
    model: str | None = None  # 생성이면 모델 ID
    source: str | None = None  # 제공 파일이면 경로/출처


class UserInputEcho(BaseModel):
    """원본 유저 입력을 되비춘다(report.md 앞단)."""

    objective: str
    character_input: str | None = None
    product_input: str | None = None
    reference_ref: str | None = None
    raw_brief: str | None = None


class NodePrompt(BaseModel):
    node: str
    prompt: str
    model: str | None = None


class CostLine(BaseModel):
    """예상 비용 한 줄. 모델별 단가 x 실사용량으로 소계를 낸다(cost.py)."""

    label: str  # 항목(패널 스틸 / 영상 클립 / BGM / 나레이션 / 효과음 / 품질 평가)
    model: str  # 실제·유효 모델 ID 또는 로컬 백엔드명(ken_burns/synth)
    unit: str  # 초 / 장 / 1k자 / 호출 / 클립
    quantity: float
    unit_price_usd: float
    subtotal_usd: float
    note: str | None = None


class CostReport(BaseModel):
    """회차 예상 비용. 공개 단가 근사치 기반이라 실제 청구와 다를 수 있다."""

    as_of: str  # 단가 기준일(cost.PRICING_AS_OF)
    currency: str = "USD"
    lines: list[CostLine] = Field(default_factory=list)
    total_usd: float = 0.0
    caveats: list[str] = Field(default_factory=list)


class FinalReport(BaseModel):
    """최종 결과 리포트. report 노드 산출, report.md로 렌더."""

    run_id: str
    user_input: UserInputEcho
    node_prompts: list[NodePrompt] = Field(default_factory=list)
    final_opinion: str = ""  # 결과 영상 종합 의견(LLM)
    node_flow: list[str] = Field(default_factory=list)  # 노드 그래프 흐름
    models_used: dict = Field(default_factory=dict)  # 용도별 모델 ID와 lane
    bgm_source: BgmReport = Field(default_factory=BgmReport)
    conformance: dict = Field(default_factory=dict)  # pass 여부와 체크 요약
    rubric: dict = Field(default_factory=dict)  # gated/flat과 D1~D7
    # verify repair 요약: 되돌린 횟수와 진행 시점에 남은 fail 코드(증거 보존).
    repair: dict = Field(default_factory=dict)
    viral_prediction: str = ""  # 바이럴 효과 예측(LLM)
    cost: CostReport | None = None  # 예상 비용(모델별 내역 + 합계)
    report_md: str | None = None  # 렌더된 마크다운 경로
