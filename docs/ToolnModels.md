# 도구와 모델

상태: 초안(러프 정리). 프로젝트 마무리 단계에서 다시 다듬는다. 지금은 구조와 항목을 잡는 게 목적이다.

이 문서는 무엇을 쓰는지를 세 축으로 한자리에 모은다. (1) AI 모델, (2) 외부 API, (3) 오픈소스
라이브러리. 각 항목은 "어떤 경우에 쓰는지"와 "왜 골랐는지"를 한두 줄로 적는다.

정본은 따로 있다. 모델 선택의 근거와 이력은 [../specs/ai-model-records.md](../specs/ai-model-records.md),
스택과 시스템 구조는 [../specs/trd.md](../specs/trd.md)가 가진다. 이 문서는 그 둘을 도구 관점에서
한눈에 보게 묶은 색인이고, 충돌하면 정본을 따른다.

핵심 원칙 두 가지를 먼저 둔다.

- **모델 비종속**: 모델 ID는 코드와 문서에 박지 않는다. `.env`로 주입하고 어댑터가 읽는다.
  아래 모델 이름은 현재 선택일 뿐, 백엔드를 갈아끼워도 스키마 경계 덕에 어댑터 한 곳만 바뀐다.
- **단일 필수 키**: `GEMINI_API_KEY` 하나로 분석과 이미지 생성이 돈다. 나머지 키는 옵션이고,
  해당 단계를 켤 때만 필요하다. GCP 자격이 있으면 멀티모달 호출은 Vertex lane을 우선해 크레딧을
  쓰고, 단일 키는 폴백으로 보장한다.

## 1. AI 모델

용도별로 LLM, VLM, 생성 모델을 어디에 쓰고 왜 골랐는지. 표기는 1차(기본 호출) / 폴백(막히거나
품질 부족 시) / 홀딩(검토했으나 미사용). 상세 근거는 [ai-model-records.md](../specs/ai-model-records.md).

| 용도 | 1차 모델 | 폴백/서브 | 선정 사유(요약) |
|---|---|---|---|
| 레퍼런스 비전 분석(VLM) | Gemini Flash 계열 | Gemini Pro 계열 | 빠르고 싸며 멀티모달. 분석 층은 결정론 수치가 주연이라 지각 묘사는 가벼운 모델로 충분 |
| 기획·카피 생성(LLM) | Gemini 3.1 Pro | Claude Opus(병행 비교) | 카피 품질이 결과를 좌우하는 텍스트 레인. 두 키를 다 보유해 일급으로 나란히 비교, 작업별로 나은 쪽 채택 |
| 이미지 생성(에셋 시트, 패널 스틸) | Google Nano Banana 계열(Gemini 네이티브 이미지) | 없음(단일 경로) | 단일 키 안에서 돌고, 한 이미지에 멀티뷰를 렌더링해 에셋 시트에 맞음. 스틸 품질이 영상으로 전파되므로 품질 우선. 이미지는 Nano Banana 단일 경로로 좁힘 |
| image-to-video(패널 클립) | Veo 3.1 Fast(Vertex 전용 개발 기본) | Kling O3 Pro reference-to-video(성능 최선), Kling O3 image-to-video(Veo 치환 후보), Veo 3.1 Standard/Pro(고품질 승격), 스틸 켄 번스 폴백 | 개발 검증 기본은 Veo Fast지만, 현시점 이 프로젝트에서 품질 최선은 Kling O3. 특히 O3 Pro reference-to-video가 캐릭터·제품·스토리보드 reference 일관성에서 가장 강함 |
| 배경 음악(BGM) | Lyria 3(Clip, 30초 이하 기본) | 30초 초과 시 Lyria 3 Pro, 사용자 제공 음악 또는 무음 | 컷 리듬에 BGM 템포를 맞춤. 대부분 숏폼은 30초 이하라 Clip으로 충분, 30초 넘으면 Pro로 승격 |
| voice(나레이션·발화, 되도록 사용) | voiceover 나레이션: ElevenLabs(선호) 또는 Google TTS Chirp 3 | on_camera=영상 모델 네이티브 발화(역동적 발화 컷에서만; 멀티컷+립싱크 일관은 Kling O3 Pro만) | 기본은 나레이션이다. 캐릭터 음색을 길게 연속으로 뽑아 컷이 나뉘어도 톤 일관. voice를 먼저 만들어 영상 모델에 주입하는 립싱크는 쓰지 않는다 |

비전 분석, Rubric 채점, Conformance 검사 같은 Gemini 멀티모달 호출은 `GENAI_BACKEND`가 백엔드를
고른다. 기본 `auto`는 GCP 자격이 있으면 Vertex AI(크레딧), 없으면 `GEMINI_API_KEY` lane이다.

홀딩/제외(왜 안 쓰는지): Claude 비전(단일 키 약속 위배, 분석은 결정론 수치가 우선), 게이트웨이
멀티 라우팅(현 규모에 과함), Gemini API Veo lane(Veo는 Vertex 전용으로 못박음), Veo 3.1
Lite(start/end control에서 split artifact가 생겨 품질 실망), Seedance 2.0 Fast(face/persona
reference 검열이 강해 캐릭터 reference 기반 제품 광고에서 사용성 리스크가 큼), 외부
audio/voice 파일을 영상 모델에 넣는 립싱크 경로(실측상 Seedance/Veo/Kling O3 모두 기본 채택
품질 아님), HeyGen 토킹헤드와 립싱크(범위 밖, 가장 잘 깨짐), whisperX 강제 정렬(자막은
스토리보드에서 옴). Kling O3는 제외가 아니라 성능 최선 후보이며, 개발 cycle 완료 후 사용자가
전환을 지시하면 기본 영상 경로로 올린다. 표 정본은
[ai-model-records.md](../specs/ai-model-records.md)의 "홀딩과 제외 한눈에".

## 2. 외부 API

생성 기능은 모델을 직접 박지 않고 SDK 어댑터 뒤에 둔다. 어떤 외부 서비스를 어떤 단계에서 쓰는지와
선정 사유. 스택 정본은 [trd.md](../specs/trd.md)의 "외부 서비스 클라이언트".

| 클라이언트 | 어떤 경우에 | 선정 사유 |
|---|---|---|
| google-genai | 비전 분석, 이미지 생성, Gemini 호출, Vertex AI Veo 호출 | 단일 키 약속의 중심. `GENAI_BACKEND=auto`로 Vertex(크레딧) 우선, Gemini 키 폴백을 한 SDK로 처리 |
| google-cloud-storage | Vertex Veo 출력 다운로드 | Vertex Veo 결과가 GCS로 떨어질 때 내려받는 용도 |
| fal-client | Kling O3 영상 전환 후보, Seedance 비교 후보 | `FAL_KEY`가 있으면 영상 후보 provider로. 영상은 개발 기본 경로가 아니지만, 품질 최선 후보인 Kling O3 전환 대기 경로로 둔다. 이미지에는 쓰지 않는다(Nano Banana 단일) |
| elevenlabs | voiceover TTS(서브) | voice는 되도록 사용. 캐릭터 음색 매칭과 자연스러운 감정 전달이 더 필요할 때 Google TTS 대신 |
| firecrawl-py | 제품 URL에서 정보·이미지 추출 | 컨셉 단계의 product-fetch 노드. 입력을 URL 하나로 줄이는 경로 |
| langfuse | 트레이싱·관측, 튜닝 루프 | 그래프 실행을 단계별로 기록. 키 있을 때만 붙는 옵션 sink(로컬 trace가 진실의 원천) |
| yt-dlp | 레퍼런스 영상 URL 다운로드 | 분석에 투입할 레퍼런스 확보. `utils/add-reference.sh`를 노드로 승격 |
| Tavily(옵션) | 검색 보조 | firecrawl의 보조로만. 필수 아님 |

영상 백엔드는 Veo 3.1을 Vertex AI lane으로만 호출한다(`GOOGLE_CLOUD_PROJECT`,
`GOOGLE_APPLICATION_CREDENTIALS`, `VEO_OUTPUT_GCS_URI` 필요). Veo는 절대 fal로 호출하지 않는다.

2026-07-01 smoke test 기준 운영 판단:

- 개발 검증 단계의 기본 영상 백엔드는 Vertex API의 `Veo 3.1 Fast`다. Fast가 가장 무난했고,
  짧은 뷰티 사용 컷과 `시원하다` 같은 짧은 네이티브 발화를 안정적으로 처리했다.
- 고품질 승격은 `Veo 3.1 Standard/Pro`(`veo-3.1-generate-001`)만 쓴다. 중요한 히어로 컷이나
  질감·얼굴·카메라 품질이 더 필요한 컷에서만 Fast 대신 호출한다.
- 성능상 최선의 영상 모델은 Kling O3다. 특히 `fal-ai/kling-video/o3/pro/reference-to-video`가
  여러 reference와 storyboard를 한 번에 넣는 복잡한 캐릭터 기반 제품 영상에서 가장 강했다.
  start/action image, 구체적인 캐릭터 설정 이미지, 구체적인 제품 이미지, 멀티샷 storyboard를
  prompt로 묶어 넣으면 캐릭터·제품·액션 일관성이 좋다.
- Kling O3 reference-to-video는 품질 욕심이 있거나, 일관성 있게 여러 컷을 밀어붙이고 싶거나,
  컷별 일관성이 중요한 복잡한 영상에 쓴다. 최선은 O3 Pro reference-to-video다. 더 높은 품질은
  컷별로 잘라 생성한 뒤 조립하는 방식이고, 멀티샷이 필요하면 O3 `multi_prompt`로 한 번에
  생성할 수도 있다.
- Kling O3 image-to-video도 충분히 좋다. `image_url`에 시작 이미지를, `end_image_url`에 끝
  이미지를 넣을 수 있어 Veo 3.1 image-to-video와 치환하기 쉽다. 명확한 A→B 액션 컷은 이 경로가
  강하다.
- `Veo 3.1 Lite`는 기본 후보에서 내린다. 단일 start image 제품 데모는 가능했지만,
  start/end control board에서 split-screen artifact를 만들었고 결과가 실망스러웠다.
- Veo는 **start image를 넣어야 한다.** 텍스트만으로는 제품, 캐릭터, 시작 동작, 끝 상태가
  안정적으로 고정되지 않는다. 먼저 Nano Banana로 컷별 key image를 만들고 그 이미지를
  image-to-video에 넣는다.
- start image가 이후 상태를 충분히 담기 어렵다면 Nano Banana로 start/end keyframe board를
  만든다. 이때 프롬프트에 "왼쪽은 시작, 오른쪽은 끝 상태이며 최종 영상은 split-screen이 아닌
  하나의 full-screen shot"이라고 명확히 설명하고, negative prompt에도 split-screen/collage를
  금지한다. 이 방식은 Fast와 Standard/Pro에서 잘 먹혔고 Lite에서는 깨졌다.
- 외부 audio/voice input을 립싱크용으로 주입하는 방식은 아직 어렵다. Seedance 2.0 reference
  audio는 대사 drift가 있었고, Veo 3.1 audio input도 기본 채택하기 어렵고, Kling O3의
  `voice_id` binding도 기대보다 약했다.
- 립싱크가 필요하면 영상 모델에 대사 스크립트와 목소리 지시를 직접 넣어 네이티브 발화를
  생성한다. 이 방식은 어느 모델이든 어느 정도 자연스럽다.
- 다만 현재 개발 검증 cycle이 끝나기 전까지 기본 모델은 Veo 3.1 Fast로 유지한다. 사용자가
  "Kling으로 가자"고 명시하면 그때 기본 영상 모델을 Kling O3로 전환한다.
- Seedance 2.0 Fast는 영화적인 연출과 기존 촬영본 확장 잠재력은 있지만, storyboard + persona
  character fit + product reference 테스트에서 얼굴/인물 reference가 provider validation에
  막혔다. 이 프로젝트처럼 캐릭터 reference가 중요한 영상 생성에는 사용이 어렵다.

## 3. 오픈소스 및 라이브러리

`pyproject.toml`에 들어간 패키지를 용도별로 묶는다. 시스템 구조 정본은 [trd.md](../specs/trd.md)의
"핵심 스택".

### 코어와 경계

| 라이브러리 | 용도 |
|---|---|
| langgraph | 오케스트레이션. 단계를 노드로, 사람 확인 지점을 interrupt로 표현. 게이트 ask/pass/run을 그래프 위에서 일반화 |
| pydantic | 스키마 경계. 분석과 생성이 통신하는 유일한 인터페이스. 백엔드를 갈아끼워도 스키마는 고정 |
| typer + rich | CLI. 챗 모드와 런 모드, `execute` 직행 명령. 코어를 같은 프로세스에서 직접 호출 |

### 영상 분석(결정론 층)

| 라이브러리 | 용도 |
|---|---|
| scenedetect | 컷 분포 검출 |
| librosa(+ numba) | 오디오 다이내믹 분석 |
| opencv-python | 팔레트, 밝기 추출 |
| numpy | 수치 연산 토대 |

### 영상 조립과 자막

| 라이브러리 | 용도 |
|---|---|
| ffmpeg(시스템 의존성) | 조립의 토대. concat, 자막 오버레이, 음악 mux, 워터마크. 파이썬 패키지가 아니라 OS에 설치 |
| moviepy | 패널 클립 결합과 편집 |
| pillow + pilmoji | 컬러 이모지를 살린 투명 자막 PNG 렌더, ffmpeg로 타이밍에 맞춰 오버레이 |

### 외부 호출과 설정

| 라이브러리 | 용도 |
|---|---|
| google-genai, google-cloud-storage, fal-client, elevenlabs, firecrawl-py, langfuse, yt-dlp | 외부 서비스 어댑터(2번 표 참고) |
| tenacity | 외부 호출 재시도 백오프 |
| python-dotenv | `.env`에서 키와 모델 ID 주입 |

### 개발 도구

| 라이브러리 | 용도 |
|---|---|
| pytest | 테스트 |
| ruff | 린트, 포매팅 |
| mypy | 타입 체크 |

런타임은 Python 3.10 이상, 의존성은 uv로 관리한다.

## 마무리 단계 할 일(이 문서)

- 실제로 채택해 돌려 본 모델만 남기고, 병행 비교(Gemini 3.1 Pro vs Claude Opus) 결과를 회고와 맞춰 정리.
- 각 선정 사유를 한두 줄로 압축, 표 중복 제거.
- 최종 `.env.example` 키 이름과 표의 모델·클라이언트를 대조해 누락 점검.
