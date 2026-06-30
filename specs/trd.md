# TRD: 기술 스택과 시스템 구조

상태: 확정. 이 문서는 무엇으로 만드는지(라이브러리, 외부 클라이언트, 실행 환경)와 그것들이
어떤 구조로 묶이는지를 정한다. 무엇을 만드는지는 [project-brief.md](project-brief.md)와
[prd.md](prd.md)에, 사용자 경험과 명령은 [product-design.md](product-design.md)에, 생성
단계 내부 계약은 [../docs/pipeline-design.md](../docs/pipeline-design.md)에 있다. 스택 선택의
긴 근거와 대안 비교는 [../docs/references-implementation.md](../docs/references-implementation.md)를
본다.

## 한 줄 요약

Python으로 짠 로컬 CLI다. 코어는 **LangGraph** 그래프로 단계와 게이트를 표현하고, 클라이언트는
**typer**와 rich로 그 코어를 같은 프로세스에서 직접 호출한다. 외부 생성 기능(이미지, 영상,
음성, URL 추출)은 각자의 SDK 어댑터 뒤에 두고, 단계 사이는 pydantic 스키마로만 통신한다.

## 핵심 스택

| 영역 | 라이브러리 | 역할 |
|---|---|---|
| 오케스트레이션 | **LangGraph** | 단계를 노드로, 사람 확인 지점을 `interrupt`로 표현. 게이트 ask/pass/run을 그래프 위에서 일반화 |
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
| **google-genai** | 비전 분석, 이미지 생성, Gemini API 호출, Vertex AI Veo 호출 | 분석/이미지/Lyria는 Gemini API key lane, 영상은 Vertex lane 우선 |
| **google-cloud-storage** | Vertex Veo 출력 다운로드 | Vertex Veo 출력이 GCS로 떨어질 때 내려받기 |
| **fal-client** | 선택 이미지/영상 백엔드 | `FAL_KEY`가 있으면 Flux 이미지 후보와 Seedance/Kling 영상 후보를 실험 provider로 쓴다 |
| **elevenlabs** | 보이스오버 TTS(옵션) | 기본은 꺼짐. 데모 1편에서만 |
| **firecrawl-py** | 제품 URL에서 정보와 이미지 추출 | 컨셉 단계의 product-fetch 노드 |
| **langfuse** | 트레이싱과 관측, 튜닝 루프 | 그래프 실행을 단계별로 기록 |
| **yt-dlp** | 레퍼런스 영상 URL을 내려받아 분석에 투입 | `utils/add-reference.sh`를 노드로 승격 |

영상 백엔드는 `VIDEO_PROVIDER`가 비어 있으면 Vertex AI Veo를 기본으로 둔다. Google Cloud 크레딧을 쓰려면
`GOOGLE_CLOUD_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS`, `VEO_OUTPUT_GCS_URI`가 필요하다.
GCS 출력 위치는 `VEO_OUTPUT_GCS_URI` 하나로 통일한다.
Gemini API Veo는 Vertex가 없을 때의 폴백이다. fal.ai는 `FAL_KEY`가 있을 때 Flux 이미지와
Seedance/Kling image-to-video 후보를 실험 provider로 붙인다. 검색이 필요하면 Tavily를 firecrawl의 보조로
붙일 수 있으나 필수는 아니다.

## 시스템 구조 (요약)

세 레이어로 나눈다. 각 레이어는 아래 레이어를 모르고, 통신은 pydantic 스키마로만 한다.

```
CLI (typer + rich)            chat / run / execute, 게이트 제어 플래그
   │  인프로세스 직접 호출
   ▼
코어 그래프 (LangGraph)       노드 = 단계, interrupt = 게이트
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
  단독 CLI(`verify`/`evaluate`)다. 자세한 건 아래 "테스트 전략"과
  [conformance-gate.md](conformance-gate.md), [rubric.md](rubric.md).
- **두 층 분석**: 결정론적 로컬 층(scenedetect, librosa, opencv)이 재현 가능한 수치를 내고,
  멀티모달 층이 지각적 설명을 더한다. 결정론 수치는 지각 층이 덮어쓰지 않는다.
- **게이트 일반화**: 모든 중요한 단계 뒤에 확인 인터럽트를 둔다. ask(챗 기본), pass
  (`--force-step-pass <step>`), 런 모드(전부 통과)가 같은 그래프 위에서 동작한다.
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
- **립싱크와 토킹 모델 제외.** 주 경로는 자막에 뮤직 베드다. 보이스오버는 옵션 데모 1편.
- **키 비커밋.** 키는 `.env`에만 둔다. `.env.example`은 이름과 발급처, 용도만 담고 값은
  비운다. 채점자가 자기 키를 꽂아 실행할 수 있어야 한다.
- **런타임.** Python 3.10 이상. 의존성은 [uv](https://docs.astral.sh/uv/)로 관리한다.

## 테스트 전략

검증은 두 층이다. 일반 개발 테스트와, 노드그래프 최종 단계의 두 검증 게이트다.

### 개발 테스트(기본)

- `pytest`로 결정론 층을 실제 단언으로 덮는다. 외부 모델 호출(Gemini, 영상 백엔드 등)은
  목으로 막는다. 단위 테스트는 독립이고 데이터를 스스로 만든다.
- 일련의 변경 뒤에는 `ruff check`, `ruff format`, `mypy`, `pytest -q`를 돌린다.
- 영상이 필요한 테스트는 `reference_video/` 아래 mp4를 쓰고, 없으면 skip한다.

### 두 검증 게이트(노드그래프 최종 단계)

영상 단계 뒤에 검증 게이트를 둘 둔다. 순서가 있다.

1. **Conformance 게이트**(하드 pass/fail): 결과물이 의도한 템플릿대로 기술적으로 온전히
   만들어졌고 노드 산출물이 빠짐없이 머지됐나. 먼저 돈다. 계약은
   [conformance-gate.md](conformance-gate.md).
2. **Rubric 게이트**(소프트 0~100): conformance를 통과한 뒤, 콘텐츠로서 먹히나. 계약은
   [rubric.md](rubric.md).

conformance가 fail이면 rubric 채점으로 가지 않고, 결함 카테고리로 해당 샷 재생성을
트리거한다. 두 게이트는 ask(챗 기본), pass(`--force-step-pass`), 런 모드(전부 통과)와 같은
그래프 위에서 동작한다(게이트 일반화).

### 이중 용도: 그래프 노드이자 단독 명령

두 게이트는 그래프 안의 노드 역할인 동시에, 단독 CLI로도 떼어 돌릴 수 있어야 한다. 그래프가
아직 미구현이어도 단독 명령은 지금 동작한다.

- `reel-gen verify <video> [--input ... --storyboard ... --manifest ...]` — conformance.
- `reel-gen evaluate <video>` — rubric.

레퍼런스 영상에 지금 바로 적용 가능하다. 레퍼런스는 템플릿/매니페스트가 없어 conformance의
intrinsic 체크만 돌고(나머지 skip), 잘 만든 레퍼런스는 모두 PASS여야 한다. 이를 회귀 기준선
으로 쓴다.

### 게이트 테스트 방식

- **결정론 체크**(미디어 무결성, 템플릿 적합성, 볼륨 LUFS/클리핑, 머지 무결성, 스키마 검증,
  rubric 수식): 실제 단언으로 덮는다. 합성한 깨진/블랙/무음 클립으로 `fail`을, 합성
  `RunManifest`/`Storyboard`로 머지 위반을 단언한다.
- **VLM/지각 체크**(자막 위치·효과·전환): 외부 호출이라 목으로 막는다. 키가 없으면 `skip`
  이고 skip은 통과로 치므로 게이트가 키 부재로 막히지 않는다.
- **레퍼런스 골든**: 레퍼런스 영상이 conformance PASS이고 rubric 기준선 점수가 나오는지를
  확인하고, 결과를 `evals/`(conformance는 `evals/conformance/`)에 남긴다. `evals/`는
  gitignore라 재생성 가능한 산출물로 둔다.

## 다음 작업 순서

1. `pyproject.toml`에 위 "설치 필요" 묶음 반영(`langgraph` 먼저).
2. product-fetch(firecrawl)와 reference-fetch(yt-dlp) 노드를 그래프에 배선.
3. 영상 단계를 `VideoBackend` 인터페이스 하나에 Vertex Veo 우선, Gemini API Veo 폴백
   어댑터로 구현.
