# TRD: 기술 스택과 시스템 구조

상태: 확정. 이 문서는 무엇으로 만드는지(라이브러리, 외부 클라이언트, 실행 환경)와 그것들이
어떤 구조로 묶이는지를 정한다. 무엇을 만드는지는 [project-brief.md](project-brief.md)와
[prd.md](prd.md)에, 사용자 경험과 명령은 [product-design.md](product-design.md)에, 생성
단계 내부 계약은 [../docs/pipeline-design.md](../docs/pipeline-design.md)에 있다.

## 한 줄 요약

Python으로 짠 로컬 CLI다. 코어는 **LangGraph** 그래프로 생성 단계를 표현하고, 클라이언트는
**typer**와 rich로 그 코어를 같은 프로세스에서 직접 호출한다. 외부 생성 기능(이미지, 영상,
음성, URL 추출)은 각자의 SDK 어댑터 뒤에 두고, 단계 사이는 pydantic 스키마로만 통신한다.

## 핵심 스택

| 영역 | 라이브러리 | 역할 |
|---|---|---|
| 오케스트레이션 | **LangGraph** | 생성 단계를 노드로 표현하고 상태를 노드 사이로 흘린다. 단계별 사람 확인 게이트는 두지 않는다(HITL은 향후) |
| CLI | **typer** + rich | 챗 모드와 런 모드, `execute` 직행 명령. 코어를 인프로세스 직접 호출(서버 없음) |
| 스키마 경계 | **pydantic** | 분석과 생성이 통신하는 유일한 인터페이스. 백엔드를 갈아끼워도 스키마는 고정 |
| 영상 분석(정형) | scenedetect, librosa, opencv-python, numpy | 컷 분포, 오디오 다이내믹, 팔레트와 밝기를 결정론적으로 산출 |
| 영상 조립 | ffmpeg(시스템) + moviepy | 패널 클립 concat, 자막 오버레이, 음악 mux, 워터마크 |
| 자막 렌더 | pillow + pilmoji | 컬러 이모지를 살린 투명 자막 PNG. ffmpeg로 타이밍에 맞춰 오버레이 |
| 재시도 | tenacity | 외부 호출 백오프 |
| 설정 | python-dotenv | `.env`에서 키와 모델 ID 주입 |

코어(LangGraph 그래프)는 CLI와 분리된 패키지다. 미래에 웹이나 API가 같은 코어를 감싸도
비용이 들지 않게 둔다.

## 외부 서비스 클라이언트

생성 기능은 모델을 직접 박지 않고 SDK 어댑터 뒤에 둔다. **모델 ID는 이 문서에 고정하지
않는다.** `.env`로 주입하고 어댑터가 읽는다. 스키마 경계 덕에 모델이나 백엔드를 바꿔도
어댑터 한 곳만 손댄다. 용도별로 어떤 모델을 1차, 폴백, 홀딩으로 골랐는지와 그 근거는
[ai-model-records.md](ai-model-records.md)에 따로 기록한다.

| 클라이언트 | 용도 | 비고 |
|---|---|---|
| **google-genai** | 비전 분석, 이미지 생성, Gemini API 호출, Vertex AI Veo 호출 | 백엔드는 `GENAI_BACKEND`로 고른다. 기본 `auto`는 Vertex 자격이 있으면 Vertex, 없으면 Gemini API key. 영상도 Vertex lane 우선 |
| **google-cloud-storage** | Vertex Veo 출력 다운로드 | Vertex Veo 출력이 GCS로 떨어질 때 내려받기 |
| **fal-client** | 선택 영상 백엔드 | `FAL_KEY`가 있으면 Kling O3 Standard/Seedance 2.0 Fast 영상 후보를 요청 시 provider로 쓴다. 이미지에는 쓰지 않는다 |
| **elevenlabs** | 보이스오버 TTS(옵션) | 기본은 꺼짐. 데모 1편에서만 |
| **firecrawl-py** | 제품 URL에서 정보와 이미지 추출 | 컨셉 단계의 product-fetch 노드 |
| **langfuse** | 트레이싱과 관측, 튜닝 루프 | 그래프 실행을 단계별로 기록 |
| **yt-dlp** | 레퍼런스 영상 URL을 내려받아 분석에 투입 | `utils/add-reference.sh`를 노드로 승격 |

비전 분석, Rubric 채점, Conformance VLM 같은 Gemini 멀티모달 호출은 `GENAI_BACKEND`로 백엔드를
고른다. 기본 `auto`는 `GOOGLE_CLOUD_PROJECT`와 서비스계정 자격(`GOOGLE_APPLICATION_CREDENTIALS`)이
있으면 Vertex AI로 호출해 Google Cloud 크레딧을 쓰고, 자격이 없으면 `GEMINI_API_KEY`로 내려간다.
`vertex`나 `gemini`로 못박을 수도 있다. 단일 키 약속은 폴백으로 지켜져서, 채점자가 `GEMINI_API_KEY`
하나만 넣어도 분석이 돈다.

영상 백엔드는 **Veo 3.1을 Vertex AI lane으로만** 호출한다. Google Cloud 크레딧을 쓰려면
`GOOGLE_CLOUD_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS`, `VEO_OUTPUT_GCS_URI`가 필요하다.
GCS 출력 위치는 `VEO_OUTPUT_GCS_URI` 하나로 통일한다. Gemini API Veo lane은 쓰지 않는다.
fal.ai(`FAL_KEY`)는 사용자가 공식 요청할 때의 Kling O3 Standard 또는 Seedance 2.0 Fast
image-to-video에만 쓴다(이미지에는 쓰지 않고, Veo는 절대 fal로 호출하지 않는다). 영상 생성 모델 선택의
정본은 [ai-model-records.md](ai-model-records.md) 4번이며, 별도 요청 전까지 기본은
Veo 3.1 하나로 고정한다. 검색이 필요하면 Tavily를 firecrawl의 보조로 붙일 수 있으나
필수는 아니다.

**컷 길이와 멀티샷**: 생성 클립 길이는 Kling 3~15초, Veo 3.1 4~8초다. 이 프로젝트 숏폼은
보통 1~2초 컷이라 **멀티샷 생성이 기본**이다(3초 미만 단독 컷 불가). 10초 이상은 여러 번
생성해 잇되 이전 클립 마지막 프레임을 다음 start image로 재사용해 일관성을 잇는다. **BGM은
컷 주기에 bpm을 맞춰 생성**하고 컷-음악 동기를 별도 체크로 검증한다. 정본은 ai-model-records
4·5번.

## 시스템 구조 (요약)

세 레이어로 나눈다. 각 레이어는 아래 레이어를 모르고, 통신은 pydantic 스키마로만 한다.

```
CLI (typer + rich)            plan / execute / run / chat + 분석·검증 명령
   │  인프로세스 직접 호출
   ▼
코어 그래프 (LangGraph)       노드 = 생성 단계 (단계별 사람 확인 게이트 없음)
   ├─ 분석   reference -> VideoProfile (구현됨)
   └─ 생성   concept -> asset bible -> storyboard -> video -> conformance gate -> rubric gate
   │  스키마 경계 (pydantic)
   ▼
백엔드 어댑터                 이미지 / 영상(Vertex Veo, Gemini Veo) / 음성 / URL 추출 / 관측
```

- **분석과 생성의 단일 자**: 생성물을 분석기로 다시 프로파일링해 레퍼런스 프로파일과
  비교한다. 프로파일러가 곧 채점기다.
- **노드그래프 최종 검증 게이트 둘**: 영상 단계 뒤에 검증 게이트를 둘 둔다. 먼저
  conformance(하드 pass/fail, 의도대로 온전히 만들어졌나), 통과하면 rubric(소프트 0~100,
  콘텐츠로서 먹히나). 둘 다 단일 자로 레퍼런스와 생성물에 같은 코드를 댄다. 그래프 노드이자
  단독 CLI(`verify`/`evaluate`)다. 자세한 건 [testing-strategy.md](testing-strategy.md)와
  [conformance-gate.md](conformance-gate.md), [rubric.md](rubric.md).
- **두 층 분석**: 결정론적 로컬 층(scenedetect, librosa, opencv)이 재현 가능한 수치를 내고,
  멀티모달 층이 지각적 설명을 더한다. 결정론 수치는 지각 층이 덮어쓰지 않는다.
- **사람 확인은 chat만**: 그래프 안 단계별 사람 확인 게이트는 두지 않는다. plan/run 경로는
  게이트 없이 끝까지 돌고, 대화형 확인·수정은 `chat` 명령이 그래프 밖에서 한 번 담당한다.
  단계별 HITL 게이트 일반화(ask/pass/run)는 향후 과제다([../docs/Retrospective.md](../docs/Retrospective.md)).
- **저비용 폴백**: 영상 백엔드를 끄면 스틸을 켄 번스 모션으로 같은 조립 경로에 태운다.
  영상 모델 예산 없이도 끝까지 돈다.

## 설치 현황

### 이미 설치됨 (`pyproject.toml`)

google-genai, google-cloud-storage, elevenlabs, fal-client, firecrawl-py, langfuse,
langgraph, moviepy, pilmoji, yt-dlp, scenedetect, librosa, opencv-python, numpy,
pydantic, pillow, python-dotenv, typer, rich, tenacity. 개발용으로 pytest, ruff, mypy.

### 설치 필요

생성 파이프라인과 이번 세션 결정으로 추가할 것.

| 패키지 | 분류 | 왜 |
|---|---|---|
현재 추가 설치 필요 패키지는 없다.

### 시스템 의존성

- **ffmpeg**: 필수. 조립, concat, 오버레이, mux의 토대. 파이썬 패키지가 아니라 OS에 설치한다.
- 무거운 시스템 스택(cairo, pango)은 더하지 않는다. 컬러 이모지는 pilmoji로 해결하고,
  복잡한 텍스트 셰이핑이 정말 필요해질 때를 위한 폴백으로만 남긴다.

## 영상 포맷 기본값과 가드레일

별다른 이유가 없으면 아래 기본값으로 만든다. 영상 목적, 후크, 컨셉에 따라 일부는
조정할 수 있되, 가드레일은 코드가 강제한다. 기본값은 입력 스키마 `InputMeta`
(`src/reel_gen_agent/generate/schema.py`)의 디폴트로 박고, 가드레일은 같은 스키마의
밸리데이터로 검증한다. 조정은 콘셉트/후크 단계가 사유와 함께 오버라이드할 때만 적용한다.

| 항목 | 기본값 | 변경 허용 | 가드레일(코드 강제) |
|---|---|---|---|
| 종횡비 | 9:16 세로 | 없음(숏폼 고정) | 9:16 외 거부 |
| 해상도 | 1080x1920 (1080p) | 사유 있을 때 더 낮은 해상도만(예: 720x1280) | 1080x1920 초과 거부. 업스케일 금지 |
| 길이 | 14초(기본 제작 포맷, 7초 멀티샷 2개) | 목적·후크·컨셉에 따라 조정 | 0초 초과 60초 이하. 60초 초과는 무조건 거부 |
| 프레임레이트 | 30fps | 백엔드 지원·후크 의도에 맞춰 24~60 표준값 | {24, 25, 30, 50, 60} 외 거부 |
| 컨테이너/코덱 | MP4 (H.264 영상 + AAC 오디오) | 없음 | mp4/H.264/AAC 고정 |

가드레일 규칙(밸리데이터가 강제):

- **길이**: `1 <= duration_sec <= 60`, 기본 14.0(기본 제작 포맷). 통상 12~22초 대역이며,
  60 초과는 거부한다("아주 길어도 60초를 넘지 않는다"가 하드 상한). 후크·컨셉이 명시하면
  그 대역 밖으로(더 짧게 또는 60초까지) 조정할 수 있다.

### 기본 제작 포맷 (특별 요청 없을 때)

별도 요청이 없으면 아래를 기본 포맷으로 만든다(모델이 Veo든 Kling이든 유사하게 나오게).
목적·스토리보드·환경(Kling 가용 여부 등)에 따라 production 단계가 유연하게 조정한다.

- **총 14초** = 약 **7초 멀티샷 2개**를 생성해 이어붙인다(멀티샷당 컷 ~5개, **총 ~10컷**).
- **voice는 나레이션형**으로 별도 생성해 합친다(on_camera 아님).
- **자막은 키워드 중심**으로 깔끔하게.
- **BGM은 약간 업된 신나고 빠른 음악**, 컷 주기에 bpm 정렬(ai-model-records 5번).
- **인물 프레이밍은 크게 잡는다(세로형).** 이건 **기본 구도**이고 컨셉에 따라 달라질 수
  있다. 기본은 **상반신만** 나온다. **얼굴용 뷰티 제품(스킨케어, 페이스 메이크업)이면 더
  크게(더 타이트하게)** 잡아 가슴 위~얼굴이 화면을 거의 꽉 채우게 한다. 바디·의류 등은 더
  넓게. 기본값은 상반신 중심이고 얼굴용일수록 타이트하다.
- **기본 장소는 개인 본인 방이다.** 입력에 장소 언급이 없으면 등장인물의 방(실내)에서
  찍은 것으로 본다. 컨셉·제품에 따라 욕실 세면대, 카페 등으로 바뀔 수 있다.
- **기본 캐릭터는 20대 초중반 여성이다.** 특별한 이유가 없으면 자연스럽고 내추럴한 모습이
  매력 포인트인, 외모적으로 매력적인 동안의 20대 초반~초중반 여성으로 가정한다. 제품·목적이
  명시하면 바꾼다([project-brief.md](project-brief.md)의 여성향 기본과 일관).
  **이미지 생성 프롬프트에서는 평범한 일반인이 아니라 매력적인 뷰티 인플루언서/틱톡커**로
  묘사한다(매력적인 외모, 광채 피부, 트렌디한 헤어·서브틀 글램, 카메라를 사로잡는 크리에이터
  바이브). 밋밋한 일반인처럼 나오지 않게 한다.
- **두 멀티샷을 합칠 때 캐릭터가 달라지지 않도록**, 첫 번째와 두 번째 멀티샷 모두 **캐릭터
  정면샷으로 시작하는 이미지를 근거(start/reference)로** 써서 얼굴 일관성을 잡는다.

**컷 수는 정답이 없다. 위는 특별 요청이 없을 때의 기본일 뿐이다.** 포맷에 따라 유연하게
줄인다. 더 정적인 영상이나 사용자 on-camera(직접 말하는) 포맷이면 컷당 2~3초가 적당해
총 컷 수가 ~10개보다 적어진다. 목적·스토리보드·전달 방식(narration vs on_camera)에 맞춰
production 단계가 컷 수와 컷 길이를 정한다.
- **해상도**: `width <= 1080`, `height <= 1920`, 9:16 비율 유지. 1080p가 상한이자
  기본이다. 더 낮은 해상도는 사유(백엔드 한계, 빠른 반복 등)가 있을 때만 허용하고,
  1080p를 넘는 업스케일은 거부한다.
- **프레임레이트**: 기본 30. 30을 강제하지는 않는다. 영상 백엔드에 따라 24fps만
  내는 모델(예: Seedance 계열)도 있어, 표준값 {24, 25, 30, 50, 60}을 허용한다.
  그 외 값은 거부한다. 백엔드가 내는 실제 fps를 메타에 그대로 반영하고 conformance가
  `fps_tolerance` 안에서 합치 여부를 검증한다.
- **종횡비·컨테이너**: 9:16과 mp4(H.264/AAC)는 고정이다. 조립 단계(ffmpeg)는 이
  컨테이너·코덱으로 인코딩한다.

`InputMeta`의 현재 디폴트(`duration_sec`, `fps`, `aspect_ratio`)를 이 표에 맞춘다
(`duration_sec` 기본 18.0). 해상도 기본·상한은 `InputMeta`에 명시 필드로 추가하고,
조립 단계가 이 값으로 인코딩·검증하도록 한다. 이 포맷 적합성은 conformance 게이트의
intrinsic 체크와도 맞물린다(의도한 포맷대로 온전히 만들어졌나).

## 제약 조건

- **로컬 실행 전제.** 서버리스에는 ffmpeg가 없고 타임아웃과 파일시스템 제약으로 영상
  파이프라인이 돌지 않는다. 공개 배포(Vercel 등)와 웹 프론트엔드는 범위 밖이다.
- **서버 없음.** CLI가 코어를 같은 프로세스에서 직접 호출한다. FastAPI 같은 별도 서버를 두지
  않는다. 한 줄 실행이 목표다.
- **스키마가 유일한 경계.** 분석 내부 구현에 생성 단계가 직접 묶이면 안 된다. 백엔드 교체가
  여러 단계로 번지면 설계를 다시 본다.
- **모델 비종속.** 모델 ID와 백엔드는 `.env`로 주입한다. 코드와 이 문서는 특정 모델에
  묶이지 않는다.
- **결정론 층 보존.** 로컬 측정값(컷, 오디오, 팔레트)은 멀티모달 설명이 덮어쓰지 않는다.
  테스트는 결정론 층을 실제 단언으로 덮고, 외부 모델 호출은 목으로 막는다.
- **voice 되도록 사용, 전용 립싱크 미구현.** voice는 캐릭터 매칭으로 되도록 쓴다
  (on_camera=영상 모델 네이티브 발화, voiceover=별도 TTS, none=음악 베드만). 전용 립싱크
  아바타는 만들지 않고 영상 모델 네이티브 발화만 활용한다. 자막+뮤직 베드는 폴백
  ([ADR.md](ADR.md) ADR-0012).
- **키 비커밋.** 키는 `.env`에만 둔다. `.env.example`은 이름과 발급처, 용도만 담고 값은
  비운다. 채점자가 자기 키를 꽂아 실행할 수 있어야 한다.
- **런타임.** Python 3.10 이상. 의존성은 [uv](https://docs.astral.sh/uv/)로 관리한다.

## 테스트와 관측

검증은 세 계층이다. 결정론 단위 테스트가 토대를 깔고, 두 검증 게이트(conformance →
rubric)가 결과물을 판정하며, 레퍼런스 골든이 회귀 기준선을 잡는다. 외부 모델 호출은
목으로 막고 결정론 층은 실제 단언으로 덮는다. 두 게이트는 그래프 노드이자 단독
CLI(`verify`/`evaluate`)다. 테스트 정본은 [testing-strategy.md](testing-strategy.md).

실행 기록은 로컬 trace가 진실의 원천이고 항상 켜진다. Langfuse는 키가 있을 때만 붙는
옵션 sink다. 로그는 `logs/<session_id>/<run_id>/`에 `trace.jsonl`(구조화)과
`run.log`(사람 판독)로 남는다. 로깅 정본은 [logging-strategy.md](logging-strategy.md).

## 다음 작업 순서

1. `pyproject.toml`에 위 "설치 필요" 묶음 반영(`langgraph` 먼저).
2. product-fetch(firecrawl)와 reference-fetch(yt-dlp) 노드를 그래프에 배선.
3. 영상 단계를 `VideoBackend` 인터페이스 하나에 Veo 3.1 Lite(Vertex lane 전용) 어댑터로
   구현한다. Kling O3 Standard/Seedance 2.0 Fast(fal lane)는 사용자 공식 요청 시 같은
   인터페이스 뒤에 붙인다.
