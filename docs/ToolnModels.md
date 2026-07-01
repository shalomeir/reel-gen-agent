# 도구와 모델

이 문서는 프로젝트가 쓰는 도구를 세 축으로 모은 색인이다. (1) AI 모델, (2) 외부 API,
(3) 오픈소스 라이브러리. 각 항목에 어떤 경우에 쓰는지와 왜 골랐는지를 한두 줄로 적는다.

정본 모델 선택 근거와 이력은 [../specs/ai-model-records.md](../specs/ai-model-records.md) 문서에 있다.
스택과 시스템 구조는 [../specs/trd.md](../specs/trd.md)가 가진다. 이 문서는 그 둘을 도구
관점에서 요약한다.

핵심 원칙 두 가지를 먼저 둔다.

- **모델 비종속**: 모델 ID는 코드와 문서에 박지 않는다. `.env`로 주입하고 어댑터가 읽는다. 동일 유형에서 어떤 모델을 우선할지 역시 `.env` 설정을 따른다.
  아래 모델 이름은 현재 default 우선순위일 뿐이다.
- **단일 필수 키**: `GEMINI_API_KEY` 하나로 분석과 이미지 생성, 영상 생성 등 필수적인 모든 기능이 동작한다. 나머지 키는 옵션이고
  해당 단계를 켤 때만 필요하다. GCP 자격이 있으면 멀티모달 호출은 Vertex 레인을 우선해 GCP 크레딧을
  쓰고, 단일 키는 폴백으로 보장한다.

## 1. AI 모델

용도별로 LLM, VLM, 생성 모델을 어디에 쓰고 왜 골랐는지 정리한다. 표기는 1차(기본 호출),
폴백(막히거나 품질이 부족할 때), 홀딩(검토했으나 미사용)으로 나눈다. 상세 근거는
[ai-model-records.md](../specs/ai-model-records.md)에 있다.

| 용도 | 1차 모델 | 폴백/서브 | 선정 사유(요약) |
|---|---|---|---|
| 레퍼런스 비전 분석(VLM) | Gemini Flash 계열 | Gemini Pro 계열 | 빠르고 싸며 멀티모달이다. 분석 층은 결정론 수치가 주연이라 지각 묘사는 가벼운 모델로 충분하다 |
| 기획과 카피 생성(LLM) | Gemini 3.1 Pro | Claude Opus(병행 비교) | 카피 품질이 텍스트 레인의 결과를 좌우한다. 두 키를 다 보유해 나란히 비교하고, 작업마다 나은 쪽을 쓴다 |
| 이미지 생성(에셋 시트, 패널 스틸) | Google Nano Banana 계열(Gemini 네이티브 이미지) | 없음(단일 경로) | 단일 키 안에서 돌고, 한 이미지에 여러 뷰를 렌더해 에셋 시트에 맞는다. 스틸 품질이 영상으로 이어지므로 품질을 우선한다 |
| image-to-video(패널 클립) | Kling O3 Pro image-to-video | Kling O3 Standard, Veo 3.1 Fast(Vertex/Gemini), Veo 3.1 Standard/Pro(고품질 승격), Seedance 2.0 Fast, 스틸 켄 번스 | 현시점 품질 최선이 Kling O3 Pro image-to-video다. 시작 이미지로 등장 인물과 제품을 고정하기 쉽고 움직임이 자연스럽다. Veo 3.1 Fast는 Vertex 자격이 있을 때 폴백으로 둔다 |
| 배경 음악(BGM) | Lyria 3(Clip, 30초 이하 기본) | 30초 초과 시 Lyria 3 Pro, 사용자 제공 음악 또는 무음 | 컷 리듬에 BGM 템포를 맞춘다. 숏폼은 대개 30초 이하라 Clip으로 충분하고, 30초를 넘으면 Pro로 올린다 |
| voice(나레이션과 발화, 되도록 사용) | voiceover 나레이션: ElevenLabs `eleven_v3`(한국어와 영어 공통 기본, Google TTS보다 낫다. 없을 때만 Google TTS 3.1 preview 폴백) | on_camera는 영상 모델 네이티브 발화(역동적 발화 컷에서만. 멀티컷 립싱크 일관은 Kling O3 Pro만 가능) | 기본은 나레이션이다. 톤은 광고 카피가 아니라 크리에이터의 1인칭 경험담으로 쓴다. 레퍼런스 발화의 톤과 속도가 있으면 eleven_v3 오디오 태그로 전달한다. 컷이 나뉘어도 톤을 유지한다 |
| 효과음(SFX) | 씬 자연음: 영상 모델 네이티브 오디오(Veo `generate_audio`, 거의 항상 켜서 무음 영상을 피한다) | 비-diegetic 편집 효과음(전환 whoosh, 그래픽 액센트, 후크 riser, 엔딩 징글): ElevenLabs `text_to_sound_effects`(옵션) | 씬 안의 소리는 영상 모델이 맥락째 내는 게 낫다. 예능식 편집 효과음만 플랜이 켤 때 따로 생성해 조립 단계에서 loudnorm으로 눅여 얹는다 |
| BGM/voice/SFX 믹스 | ffmpeg amix + loudnorm(-16 LUFS) | - | 나레이션이 있으면 BGM을 덕킹하고(prominence 따름), 없으면 BGM이 주연이다. 네이티브 오디오는 낮은 앰비언스로만 쓰고 덕킹 트리거로 삼지 않는다. 클리핑 방지로 최종 정규화한다 |

비전 분석, Rubric 채점, Conformance 검사 같은 Gemini 멀티모달 호출은 `GENAI_BACKEND`에서 처리된다. 기본 `auto`는 GCP 자격이 있으면 Vertex AI(크레딧)를, 없으면 `GEMINI_API_KEY` 레인을 쓴다.

홀딩과 제외(왜 안 쓰는지):
게이트웨이 멀티 라우팅(현 규모에 과함), Veo 3.1 Lite(start/end control에서 split artifact가
생겨 품질이 실망스러움), Kling O3 reference-to-video(여러 reference를 넣어 봤으나 생성 퀄리티가
기대에 못 미쳐 기본 경로에서 제거), Seedance 2.0 Fast(얼굴과 인물 reference 검열이 강해 캐릭터
reference 기반 제품 광고에서 자주 막히는 리스크가 있어서 제외), 외부 audio/voice 파일을 영상 모델에 넣는
립싱크 경로 (실측상 Seedance, Veo, Kling O3 모두 기본으로 채택하기 어려움. 일관성을 가진 목소리 생성이 어려움. voice 를 주입하면 더 어색함.), HeyGen 토킹헤드와 립싱크(범위 밖이고 가장 잘 깨짐), whisperX 강제 정렬(자막은 스토리보드에서 온다). 표 정본은
[ai-model-records.md](../specs/ai-model-records.md)의 "홀딩과 제외 한눈에"에 있다.

## 2. 외부 API

생성 기능은 모델을 직접 박지 않고 SDK 어댑터 뒤에 둔다. 어떤 외부 서비스를 어떤 단계에서 쓰는지와
선정 사유를 적는다. 스택 정본은 [trd.md](../specs/trd.md)의 "외부 서비스 클라이언트"에 있다.

| 클라이언트 | 어떤 경우에 | 선정 사유 |
|---|---|---|
| google-genai | 비전 분석, 이미지 생성, Gemini 호출, Vertex AI Veo 호출 | 단일 키 약속의 중심이다. `GENAI_BACKEND=auto`로 Vertex(크레딧)를 우선하고 Gemini 키 폴백까지 한 SDK로 처리한다 |
| google-cloud-storage | Vertex Veo 출력 다운로드 | Veo 결과가 GCS로 떨어질 때 내려받는 용도다 |
| fal-client | Kling O3 영상 기본 경로(image-to-video), Seedance 비교 후보 | `FAL_KEY`가 있으면 기본 영상 provider로 Kling O3 Pro를 쓴다. 이미지에는 쓰지 않는다(Nano Banana 단일) |
| elevenlabs | voiceover TTS(`text_to_speech`)와 편집 효과음(`text_to_sound_effects`, 옵션) | voice는 되도록 쓴다(Google TTS보다 감정과 음색이 자연스러움). SFX는 비-diegetic 편집 효과음만 따로 생성한다 |
| firecrawl-py | 제품 URL에서 정보와 이미지 추출 | 컨셉 단계의 product-fetch 노드다. 입력을 URL 하나로 줄이는 경로다 |
| langfuse | 트레이싱과 관측, 튜닝 루프 | 그래프 실행을 단계별로 기록한다. 키가 있을 때만 붙는 옵션 sink이고, 로컬 trace가 진실의 원천이다 |
| yt-dlp | 레퍼런스 영상 URL 다운로드 | 분석에 넣을 레퍼런스를 확보한다. `utils/add-reference.sh`를 노드로 승격한 것이다 |
| Tavily(옵션) | 검색 보조 | firecrawl의 보조로만 쓴다. 필수가 아니다 |

영상 백엔드에서 Veo 3.1은 Vertex AI 레인으로만 호출한다(`GOOGLE_CLOUD_PROJECT`,
`GOOGLE_APPLICATION_CREDENTIALS`, `VEO_OUTPUT_GCS_URI` 필요). Veo는 fal로 호출하지 않는다.

- 기본 영상 모델은 Kling O3 Pro image-to-video다(`fal-ai/kling-video/o3/pro/image-to-video`,
  `VIDEO_MODEL_PRIORITY` 최상단). 등장 모델의 일관성을 잡기 쉽고, `image_url`에 시작 이미지를,
  `end_image_url`에 끝 이미지를 넣을 수 있어 Veo 3.1 image-to-video와 치환하기 쉽다. 명확한
  A에서 B로 가는 컷은 이 방식이 확실히 편하다.
- Kling O3 reference-to-video는 버린다. 초기에는 캐릭터와 제품 reference를 넣어 컷별 정체성
  고정까지 붙여 봤지만, 실제 생성 퀄리티가 기대에 크게 못 미쳐 기본 경로와 `.env.example`
  우선순위에서 뺐다.
- `Veo 3.1 Lite`는 기본 후보에서 내린다. 단일 start image 제품 데모는 됐지만, start/end control
  board에서 split-screen artifact를 만들었고 결과가 실망스러웠다.
- Veo는 **start image를 넣어야 한다.** 텍스트만으로는 제품, 캐릭터, 시작 동작, 끝 상태가
  안정적으로 고정되지 않는다. 먼저 Nano Banana로 컷별 key image를 만들고 그 이미지를
  image-to-video에 넣는다.
- start image가 이후 상태를 충분히 담기 어렵다면 Nano Banana로 start/end keyframe board를
  만든다. 이때 프롬프트에 "왼쪽은 시작, 오른쪽은 끝 상태이며 최종 영상은 split-screen이 아닌
  하나의 full-screen shot"이라고 명확히 설명하고, negative prompt에도 split-screen과 collage를
  금지한다. 이 방식은 Fast와 Standard/Pro에서 잘 먹혔고 Lite에서는 깨졌다.
- 외부 audio/voice input을 립싱크용으로 주입하는 방식은 아직 어렵다. Seedance 2.0 reference
  audio는 대사 drift가 있었고, Veo 3.1 audio input도 기본으로 채택하기 어렵고, Kling O3의
  `voice_id` binding도 기대보다 약했다.
- 립싱크가 필요하면 영상 모델에 대사 스크립트와 목소리 지시를 직접 넣어 네이티브 발화를
  생성한다. 이 방식은 어느 모델이든 어느 정도 자연스럽다.
- Seedance 2.0 Fast는 영화적 연출과 기존 촬영본 확장 잠재력은 있지만, storyboard와 persona
  character fit, product reference 테스트에서 얼굴과 인물 reference가 provider validation에
  막혔다. 이 프로젝트처럼 캐릭터 reference가 중요한 영상 생성에는 쓰기 어렵다.

## 3. 오픈소스 및 라이브러리

`pyproject.toml`에 들어간 패키지를 용도별로 묶는다. 시스템 구조 정본은 [trd.md](../specs/trd.md)의
"핵심 스택"에 있다.

### 코어와 경계

| 라이브러리 | 용도 |
|---|---|
| langgraph | 오케스트레이션. plan과 execute를 노드 StateGraph로 짠다. execute는 visuals 다음에 voice, bgm, sfx를 병렬로 만들고(fan-out) assemble에서 합친다(fan-in). 확인 게이트(HITL)는 없고 run으로 한 번에 돈다 |
| pydantic | 스키마 경계. 분석과 생성이 통신하는 유일한 인터페이스다. 백엔드를 갈아끼워도 스키마는 고정된다 |
| typer + rich | CLI 프레임워크. `run` 일괄 실행, `plan`과 `execute` 분리, `compare` 유사도. 코어를 같은 프로세스에서 직접 호출한다 |
| prompt_toolkit | 대화형 `chat` 모드 입력 UI. 필요한 걸 물어 채우고 ReelProfile과 대표 이미지를 확인한 뒤 생성한다(대화형 인테이크와 확인 1회) |

### 영상 분석(결정론 층)

| 라이브러리 | 용도 |
|---|---|
| scenedetect | 컷 분포 검출 |
| librosa(+ numba) | 오디오 다이내믹 분석 |
| opencv-python | 팔레트와 밝기 추출 |
| numpy | 수치 연산 토대 |

### 영상 조립과 자막

| 라이브러리 | 용도 |
|---|---|
| ffmpeg(시스템 의존성) | 조립의 토대. concat, 자막 오버레이, 음악 mux, 워터마크. 파이썬 패키지가 아니라 OS에 설치한다 |
| pillow + pilmoji | 컬러 이모지를 살린 투명 자막 PNG를 렌더하고, ffmpeg로 타이밍에 맞춰 오버레이한다 |

### 외부 호출과 설정

| 라이브러리 | 용도 |
|---|---|
| google-genai, google-cloud-storage, fal-client, elevenlabs, firecrawl-py, langfuse, yt-dlp | 외부 서비스 어댑터(2번 표 참고) |
| tenacity | 외부 호출 재시도 백오프. 특히 Veo 일시 오류(미완료, 응답 없음)를 지수 백오프로 재시도한다(RAI 빈 결과는 원인을 진단한 뒤 프롬프트를 다시 써서 별도로 처리) |
| python-dotenv | `.env`에서 키와 모델 ID 주입 |

### 개발 도구

| 라이브러리 | 용도 |
|---|---|
| pytest | 테스트 |
| ruff | 린트, 포매팅 |
| mypy | 타입 체크 |

런타임은 Python 3.10 이상, 의존성은 uv로 관리한다.
