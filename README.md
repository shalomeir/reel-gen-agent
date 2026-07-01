# reel-gen-agent

> The English version is at the bottom of this document.

제품 하나를 인스타그램 릴스, 틱톡, 유튜브 쇼츠용으로 바로 올릴 수 있는 세로 숏폼으로
바꿔 주는 AI 에이전트 CLI다. 제품을 가리키고 참고할 스타일을 고르면, 모델과 자막과
음악이 들어간 1인 숏폼 클립을 만들어 준다. 혼자 일하는 크리에이터와 숏폼 제품 홍보,
브랜드 인지 영상을 돌리는 소규모 브랜드를 위한 도구다.

한 사람이 실내에서 몸에 걸치거나 쓰는 모습을 카메라에 담을 수 있는 제품이면 다 맞는다.
스킨케어가 가장 큰 카테고리이고(세럼과 앰플, 선크림, 토너와 모이스처라이저, 클렌저,
패치), 그다음이 메이크업(쿠션과 파운데이션, 립, 아이섀도, 세팅 스프레이)이다. 인접
뷰티, 웰니스(영양제와 다이어트, 클리닉 시술, 이너웨어와 애슬레저)도 다루고, 의류,
액세서리, 가방, 신발, 안경, 간단한 홈 데코 소품까지 확장된다. 기본값은 여성 크리에이터와
관객 쪽으로 잡는다. 숏폼 제품 PPL이 거기에 몰려 있다.

자기 API 키를 가져오면 무료로 숏폼을 만들기 시작할 수 있다. 타임라인 편집기도, 렌더
팜도 없다. 제품(또는 목적)만 주면 mp4가 나온다.

`typer`와 `rich`로 만든 CLI다. 입력 하나(`run`)를 받아 `ReelProfile`을 만들고 영상까지 한 번에
민다. 확인 게이트(HITL)는 없다. 입력이 이미 `ReelProfile`이면 바로 production으로 가고, 영상
목적이 불명확하면 거절한다.

내부에서는 안정적인 JSON 인터페이스를 통해 **분석**과 **생성**을 분리한다. 그래서 생성
백엔드를 바꿔도 나머지를 건드리지 않는다. 핵심 발상은 스타일을 하드코딩하지 않는 것이다.
레퍼런스에서 측정하고, 재사용 가능한 데이터로 표현하고, 그 데이터로 생성을 끌고 간다.
레퍼런스를 프로파일링하는 엔진이 생성된 클립도 채점하므로, 레퍼런스와 출력이 같은 잣대로
판단된다.

## 상태

- `analyze` - 구현됨. 레퍼런스 영상을 구조화된 `VideoProfile`(JSON)로.
- `add-reference` - 구현됨. URL 하나로 다운로드, 분석, 평가(Rubric), 프로필 저장, 카탈로그 기록까지. 레퍼런스 분석은 analyze + evaluate가 기본.
- `evaluate` - 구현됨. 영상을 드라이버 Rubric으로 채점(`RubricResult` JSON, 기대 효과 서술 포함). 레퍼런스와 생성물에 같은 자를 댄다. [docs/rubric.md](docs/rubric.md) 참고.
- `verify` - 구현됨. 영상이 의도대로 온전히 만들어졌는지 Conformance로 검증(하드 pass/fail). 레퍼런스 전부 PASS. [specs/conformance-gate.md](specs/conformance-gate.md) 참고.
- `run` / `plan` / `execute`(생성) - 구현됨(워킹 스켈레톤, 단계별 심화 중). 아래 참고.

## 실행 방식: 한 번에 미는 run

확인 게이트(HITL)나 챗 세션은 없다(향후 과제로 미룸). 입력 하나를 받아 `ReelProfile`을 만들고
곧장 production까지 밀어붙이는 **`run` 일괄 실행**이 기본이다.

- **`reel-gen run <입력>`**: 입력 -> `ReelProfile` -> 영상까지 한 번에. 진행 상황을 출력하고
  mp4 경로를 돌려준다. 레퍼런스가 있으면 `--max-iters`로 생성물을 다시 분석해 레퍼런스와
  **유사도를 비교하고 미달이면 재계획·재생성**한다(유사해질 때까지).
- **`reel-gen plan <입력>` / `reel-gen execute <ReelProfile>`**: 같은 파이프라인을 두 구간으로
  나눠 실행한다. 둘은 `ReelProfile` 스키마로만 통신한다.
- **`reel-gen chat`**: 대화형 챗 모드. 입력 없이 시작하면 "어떤 숏폼 영상을 만들까요?"로 열어
  목적·제품·레퍼런스·바이브를 자연스럽게 물어 채운다(prompt_toolkit). 충분해지면 ReelProfile과
  대표 이미지(key_visual)를 만들어 요약을 보여주고, **한 번 확인받은 뒤** production으로 간다.
  단계별 HITL 게이트가 아니라 입력 수집 + 최종 확인 한 번이라, 결국 run으로 수렴한다.

규칙:
- 입력이 이미 **`ReelProfile` JSON이면 계획을 건너뛰고 바로 production**을 실행한다.
- 입력에 **영상의 목적이 명확히 서술되지 않으면 실행을 거절**한다(exit≠0).
- 목적이 있으면 그 목적만으로 캐릭터·제품·환경·음악 등 **나머지를 추론해 채운다**.

### 입력 형식

`run`/`plan`의 위치 인자(`<입력>`)는 세 가지 형태를 받는다(무엇이 들어왔는지는 시스템이 판별).

- **텍스트 브리프**: 만들고 싶은 영상을 자연어로 적되, 그 안에 참고할 영상·제품·캐릭터의
  URL이나 로컬 경로를 섞어 넣는다. 시스템이 각각을 레퍼런스 / 제품 / 캐릭터로 분류한다.
- **JSON 파일 경로**: `generation_input.json`(상위 구조화 입력) 또는 완성된 `ReelProfile`
  (있으면 계획을 건너뛰고 바로 production).
- **단일 에셋(이미지·영상·URL)**: 확장자·내용으로 종류를 추정한다(영상=레퍼런스, 이미지=
  캐릭터/제품).

URL과 로컬 경로는 어느 형태에서든 섞어 쓸 수 있다. 텍스트 브리프 예시:

```bash
reel-gen run "이 제품으로 발랄한 15초 언박싱 릴 만들어줘.
제품: https://brand.example/serum
레퍼런스 영상: ./reference_video/fast-cut.mp4
캐릭터: https://example.com/model.jpg"
```

## 설치

이 도구는 빌드된 바이너리를 배포하지 않는다. 저장소를 클론한 뒤 [uv](https://docs.astral.sh/uv/)로
의존성을 깔아 쓰는 방식이다.

전제: Python 3.10+, `ffmpeg`/`ffprobe`가 PATH에, 그리고 `uv`.

```bash
# 1. 클론
git clone https://github.com/shalomeir/reel-gen-agent.git
cd reel-gen-agent

# 2. ffmpeg (분석과 영상 조립에 필요)
brew install ffmpeg            # macOS

# 3. 의존성 설치 (uv가 .venv를 만들고 reel-gen 명령을 깐다)
uv sync                        # 개발 도구까지: uv sync --extra dev

# 4. 환경 파일 준비
cp .env.example .env           # 파일명을 .env로 바꾼 뒤 API 키를 채운다

# 5. 필수 키 입력
# GEMINI_API_KEY=...            # Google AI Studio에서 발급

# 6. 확인
uv run reel-gen --help
```

설치와 실행은 `uv`로 하고, 작업은 `uv sync`가 만든 프로젝트 로컬 `.venv` 안에서
하길 권장한다. 전역 파이썬에 직접 깔지 않는 편이 의존성 충돌을 막는다. 저장소에는
이 디렉터리에서 `.venv`를 자동으로 활성화하는 `.envrc`(direnv)도 들어 있다.

가상환경을 활성화하면 `reel-gen`을 바로 부를 수 있고, 아니면 `uv run reel-gen ...`
으로 매번 감싸 실행한다.

```bash
source .venv/bin/activate      # 한 번 활성화하면
reel-gen --help                # uv run 없이 호출
```

### 업데이트

새 바이너리를 받는 게 아니라 코드를 당겨 다시 동기화한다.

```bash
git pull
uv sync
```

## 환경 설정

`.env.example`을 `.env`로 복사한 뒤 필요한 키를 채운다. 현재 실행에 필수인 API 키는
`GEMINI_API_KEY` 하나다. 이 키는 레퍼런스 영상의 비정형 분석과 Gemini 이미지 생성에 쓰인다.
GCP 자격(`GOOGLE_CLOUD_PROJECT`와 서비스계정 JSON)을 함께 채우면 비정형 분석과 멀티모달
호출이 `GENAI_BACKEND=auto` 규칙대로 Vertex AI로 돌아 Google Cloud 크레딧을 쓰고, 자격이
없으면 `GEMINI_API_KEY`로 내려간다. 키가 없으면 `reel-gen analyze --no-gemini` 같은 정형
분석만 가능하고, Gemini 기반 분석과 생성 단계는 돌릴 수 없다.

```bash
cp .env.example .env
```

`.env.example`에는 영상, TTS, 효과음, 음악 소스의 선호 순서를 적는
`TEXT_MODEL_PRIORITY`, `VIDEO_PROVIDER`, `VIDEO_MODEL_PRIORITY`, `TTS_MODEL_PRIORITY`,
`SFX_PROVIDER_PRIORITY`, `MUSIC_MODEL_PRIORITY`가
있다. 비워 두면 각 섹션의 첫 번째 기본 모델을 우선 사용한다. 텍스트 생성은 Gemini 3.1 Pro를
스토리보드, 대사 스크립트, 톤 생성 기본값으로 쓰고, 필요할 때 `TEXT_MODEL_PRIORITY`를
바꿔 Claude Opus로 전환할 수 있다. 이미지 생성은 Nano Banana(Gemini 네이티브 이미지)
단일 경로다. 별도 이미지 provider나 폴백을 두지 않는다. 영상 생성은
`VIDEO_PROVIDER`로 Vertex/Gemini API/fal 중 우선 provider를 정하고, 비워 두면 Google Cloud
크레딧을 쓸 수 있는 Vertex Veo lane을 기본으로 둔다. `GEMINI_API_KEY`를 쓰는 Gemini API Veo
lane과 `FAL_KEY`를 쓰는 fal.ai Kling O3/Seedance lane은 폴백이나 실험 provider로 둔다.
효과음은 ElevenLabs 생성 SFX를 먼저 쓰고, 사용자가 넣은 로컬 효과음, 무음 폴백 순서로
내려간다. 음악은 Lyria 3 생성 BGM, 로컬 음악, 무음 폴백 순서다. Lyria 3(Clip)은 한 번에
30초까지 생성하고, 대부분 숏폼은 30초 이하라 Clip으로 충분하다. 30초를 넘는 트랙이 필요하면
Lyria 3 Pro로 승격한다.

| 변수 | 필수 | 용도 |
|---|---|---|
| `GEMINI_API_KEY` | 예 | 멀티모달 분석 + 이미지 생성. [Google AI Studio](https://aistudio.google.com/apikey)에서 발급. |
| `ANTHROPIC_API_KEY` | 아니오 | Claude API 키. 스토리보드, 대사 스크립트, 톤 생성 옵션. |
| `GENAI_BACKEND` | 아니오 | 멀티모달 호출 백엔드. `auto`(기본)는 Vertex 자격이 있으면 Vertex, 없으면 `GEMINI_API_KEY`. `vertex`/`gemini`로 강제 가능. |
| `GEMINI_ANALYSIS_MODEL` | 아니오 | 분석 모델. 기본 `gemini-2.5-flash`. |
| `GEMINI_TEXT_MODEL` | 아니오 | Gemini 텍스트 모델. 기본 `gemini-3.1-pro-preview`. |
| `CLAUDE_MODEL` | 아니오 | Claude 텍스트 모델. 기본 `claude-opus-4-8`. |
| `TEXT_MODEL_PRIORITY` | 아니오 | 컨셉/훅/스토리보드 텍스트 모델 우선순위. 기본은 Gemini 3.1 Pro 후 Claude Opus 옵션. |
| `VIDEO_PROVIDER` | 아니오 | 영상 provider 우선순위. `vertex`, `gemini`, `fal`; 비워 두면 `vertex`. |
| `VIDEO_MODEL_PRIORITY` | 아니오 | 영상 모델 우선순위. 기본은 Vertex Veo, Gemini Veo, fal.ai Kling O3 Standard/Seedance 2.0 Fast 후보. |
| `TTS_MODEL_PRIORITY` | 아니오 | TTS 모델 우선순위. 기본은 Gemini TTS, 그다음 ElevenLabs 후보. |
| `SFX_PROVIDER_PRIORITY` | 아니오 | 효과음 소스 우선순위. 기본은 ElevenLabs 생성 SFX, 로컬 파일, 무음 폴백. |
| `MUSIC_MODEL_PRIORITY` | 아니오 | 음악 소스 우선순위. 기본은 Lyria 3, 로컬 파일, 무음 폴백. |
| `GEMINI_IMAGE_MODEL` | 아니오 | 이미지 모델(Nano Banana). 기본 `gemini-3.1-flash-image-preview`. |
| `VEO_MODEL`, `VEO_OUTPUT_GCS_URI` | 아니오 | Vertex AI image-to-video 모델과 단일 GCS 출력 prefix. 기본 `veo-3.1-lite-generate-001`. |
| `GOOGLE_CLOUD_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS` | 아니오 | Vertex AI lane(영상 Veo + 분석 멀티모달)을 쓸 때 필요한 GCP 프로젝트와 서비스 계정 JSON 절대경로. |
| `GEMINI_VEO_MODEL` | 아니오 | Gemini API image-to-video 폴백 모델. 기본 `veo-3.1-lite-generate-preview`. |
| `FAL_KEY`, `FAL_VIDEO_MODEL` | 아니오 | fal.ai 영상 provider. Kling O3 Standard/Seedance 2.0 Fast image-to-video 후보를 쓸 때 설정. |
| `LYRIA_MODEL` | 아니오 | 배경 음악 모델(생성 단계). 기본은 Lyria 3(Clip, 30초 이하), 30초 초과 트랙은 Lyria 3 Pro. |
| `ELEVENLABS_API_KEY` | 아니오 | 선택 보이스오버와 생성 효과음. SFX는 짧은 duration/count guardrail을 둔다. |
| `FIRECRAWL_API_KEY` | 아니오 | 제품 URL 정보 추출. |
| `LANGFUSE_*` | 아니오 | 실행 트레이싱과 관측. |

비정형 분석은 `GENAI_BACKEND`가 고른 백엔드(Vertex 또는 `GEMINI_API_KEY`)로 돈다. 둘 다
자격이 없으면 정형 계층이 부분 프로파일을 만들고, 지각 필드는 비워 둔다.

## 사용법

모든 명령은 `--help`로 인자와 옵션을 확인할 수 있다.

```bash
reel-gen --help                # 전체 명령 목록
reel-gen run --help            # 특정 명령의 옵션
```

### 레퍼런스 분석 (구현됨)

```bash
# 레퍼런스 영상을 분석하고 JSON을 stdout으로 출력 (로컬 경로 또는 URL)
reel-gen analyze path/to/video.mp4
reel-gen analyze "https://www.youtube.com/shorts/..."   # URL이면 먼저 내려받고 분석

# 파일로 저장하고 출처 URL 기록 (로컬 파일일 때)
reel-gen analyze path/to/video.mp4 --url "https://..." --out profiles/sample.json

# 정형 계층만 (API 키 불필요)
reel-gen analyze path/to/video.mp4 --no-gemini

# URL 하나로 레퍼런스 들이기: 다운로드 + 분석 + 평가(Rubric) + 카탈로그 (기본 둘 다 실행)
reel-gen add-reference "https://www.youtube.com/shorts/..."
reel-gen add-reference "https://..." --no-evaluate   # 분석만, 평가 건너뜀
```

유튜브/틱톡에서 레퍼런스를 `reference_video/`로 받아오는 헬퍼 스크립트도 있다.

```bash
utils/add-reference.sh "https://www.youtube.com/shorts/..."
```

### 콘텐츠 효과성 채점 (구현됨)

드라이버 Rubric으로 영상을 채점한다. 7개 차원(D1~D7)을 1~5점으로 보고, 후크·완시청은
곱셈 게이트, 나머지는 가중합 코어로 묶어 0~100점으로 환산한다. 스타일 유사도와는 다른
축이라, 닮았는지가 아니라 콘텐츠로서 먹히는지를 본다. 같은 자를 레퍼런스와 생성물에 댄다.

```bash
# 영상을 채점하고 RubricResult(JSON)를 stdout으로 출력
reel-gen evaluate path/to/video.mp4

# 파일로 저장 (evals/는 gitignore 됨)
reel-gen evaluate path/to/video.mp4 --out evals/sample.json
```

차원, 가중치, 수식, 게이트 임계값의 정본은 [specs/rubric.md](specs/rubric.md), 배경과
근거는 [docs/rubric.md](docs/rubric.md)에 있다.

### 무결성·적합성 검증 (구현됨)

영상이 의도대로 기술적으로 온전히 만들어졌는지 본다(하드 pass/fail). 미디어 무결성, 템플릿
적합성, 노드/머지 무결성, 볼륨(LUFS/클리핑), 자막 위치·효과, 컷 전환, 제품 표현, 등장인물
적합성을 결정론과 VLM으로 검사한다. 레퍼런스는 intrinsic 체크만 돌아 모두 PASS한다.

```bash
# 레퍼런스/단독 검증 (템플릿 없으면 intrinsic만)
reel-gen verify path/to/video.mp4

# 생성물 검증 (템플릿/스토리보드/매니페스트 대조)
reel-gen verify final.mp4 --input gen.json --storyboard board.json --manifest run.json

# VLM 없이 결정론 체크만
reel-gen verify path/to/video.mp4 --no-vlm
```

fail이 하나라도 있으면 exit code가 0이 아니다(게이트). 계약과 체크 카탈로그는
[specs/conformance-gate.md](specs/conformance-gate.md)에 있다.

### 영상 생성 (구현됨, 심화 중)

확인 게이트 없이 입력 하나로 끝까지 민다. 영상 목적이 없으면 거절한다.

```bash
# run: 입력 -> ReelProfile -> 영상까지 한 번에 (mp4 경로 출력)
reel-gen run "https://brand.example/serum 으로 15초 언박싱, 캐릭터 ./model.jpg"   # 텍스트 브리프
reel-gen run generation_input.json                # 구조화된 JSON 입력
reel-gen run ./reference_video/fast-cut.mp4       # 단일 에셋(영상)을 바로

# 레퍼런스가 있으면 생성물을 다시 분석해 유사도 비교, 미달이면 재계획·재생성(최대 2회)
reel-gen run "... reference: ./ref.mp4" --max-iters 2

# 이미 만든 ReelProfile을 주면 계획을 건너뛰고 바로 production
reel-gen run outputs/<run_id>/plan/ReelProfile-....json

# 두 구간으로 나눠 실행 (ReelProfile 스키마로만 통신)
reel-gen plan "..."                    # 입력 -> ReelProfile
reel-gen execute outputs/<run_id>/plan/ReelProfile-....json   # ReelProfile -> 영상

# 대화형 챗 모드: 물어보며 채우고, 요약+대표이미지 확인 후 생성
reel-gen chat                          # 빈 상태에서 대화로 시작
reel-gen chat "글로우 세럼 아침 루틴 릴"   # 시작 브리프를 주고 이어서 대화

# compare: 생성물이 레퍼런스와 같은 결인지 유사도 채점 (미달 시 exit≠0)
reel-gen compare --reference ./ref.mp4 --output outputs/<run_id>/final.mp4
reel-gen compare --reference profiles/ref.json --output profiles/gen.json --out sim.json
```

### 템플릿 직행 실행 (`execute`)

중간 단계를 건너뛰고 완성된 템플릿 JSON을 그대로 영상으로 뽑는 별도 명령이다. `run`과 입력이
헷갈리지 않게 명령을 분리했다.

```bash
reel-gen execute storyboard.json
```

`execute`가 받는 JSON은 에이전트가 스토리보드 단계에서 내놓는 것과 같은 정형 포맷이다(패널,
타이밍, 자막, 음악·워터마크 설정). 그래서 같은 JSON을 그대로 다시 주입하면 동일한 조립이
재현된다. 한 번 만든 결과를 손봐 가며 영상만 다시 뽑거나, 조립 단계를 디버그할 때 쓴다.

전제 조건: 템플릿 JSON 안의 캐릭터와 제품 카탈로그에는 영상 생성에 들어갈 **이미 생성된
이미지의 로컬 경로**가 들어 있어야 한다. `execute`는 실행 전에 그 경로들이 실제로 있는지
확인하고, 하나라도 없으면 영상을 만들 수 없으므로 그 자리에서 멈춘다(에러).

### 명령과 옵션 요약

| 명령 / 옵션 | 동작 |
|---|---|
| `--help` | 모든 명령과 하위 명령의 도움말(typer 기본). |
| `reel-gen analyze <video>` | 레퍼런스 영상을 `VideoProfile`(JSON)로 분석. |
| `reel-gen add-reference <url>` | URL로 레퍼런스 추가(다운로드, 분석, 카탈로그). |
| `reel-gen evaluate <video>` | 드라이버 Rubric으로 채점(`RubricResult` JSON, 기대 효과 서술 포함). |
| `reel-gen verify <video>` | Conformance 무결성·적합성 검증(`ConformanceReport` JSON, fail 시 exit≠0). |
| `reel-gen compare --reference <A> --output <B>` | 생성물이 레퍼런스와 같은 결인지 유사도 채점(`SimilarityReport` JSON, 미달 시 exit≠0). A/B는 `VideoProfile` JSON 또는 영상. |
| `reel-gen run ... --max-iters <n>` | 레퍼런스가 있으면 생성물을 다시 분석해 유사도를 비교하고, 미달이면 축별 델타를 피드백으로 재계획·재생성(최대 n회). |
| `reel-gen run <입력>` | 입력->ReelProfile->영상 일괄(확인 게이트 없음). ReelProfile 입력이면 바로 production, 목적 없으면 거절. |
| `reel-gen run ... --max-iters <n>` | 레퍼런스 있으면 유사도 미달 시 피드백 재계획·재생성(최대 n회). |
| `reel-gen chat` | 대화형 챗 모드. 필요한 걸 물어 채우고 ReelProfile+대표이미지 생성, 확인받고 production. |
| `reel-gen plan <입력>` | 입력 -> `ReelProfile`(profile.json). |
| `reel-gen execute <ReelProfile.json>` | ReelProfile을 곧장 영상으로. 카탈로그 이미지 로컬 경로가 없으면 멈춤. |
| `<입력>` (`run`/`plan`) | 텍스트 브리프, JSON 경로(generation_input 또는 ReelProfile), 또는 단일 에셋(이미지·영상·URL). |

## 동작 방식

두 계층이 하나의 프로파일을 만든다.

- **정형 계층**(로컬, 재현 가능): 컷 분포, 오디오 다이내믹, 색과 밝기. 유사도 채점의
  수치 근거다.
  - 컨테이너 메타데이터는 `ffprobe`
  - 컷 수, 길이 분포, 편집 모드는 PySceneDetect
  - BPM, 빌드 대 플랫 다이내믹, 인트로 무음은 librosa
  - 주요 팔레트, 밝기, 대비는 OpenCV
- **지각 계층**(Gemini 멀티모달): 보이스 톤, 전체 느낌, 자막 스타일, 훅, 내러티브 아크.

생성 파이프라인은 입력을 캐릭터·제품 에셋과 스토리보드로 펼쳐 `ReelProfile`로 동결하고
(plan), 그 프로필을 영상 모델 능력에 맞춰 재료(영상 클립·voice·bgm·sfx·자막)를 병렬로 만들고
조립·검증한다(execute). 확인 게이트 없이 `run`으로 한 번에 민다. 그래프 구조는
[specs/workflows.md](specs/workflows.md), 단계 세부는 [docs/pipeline-design.md](docs/pipeline-design.md).

레퍼런스와 생성물을 **같은 자로** 잰다. 레퍼런스를 분석하는 그 분석기가 생성물도 분석하고,
`reel-gen compare`(= `run --max-iters`의 게이트)가 두 `VideoProfile`을 축별(컷 리듬, 보이스
결, 음악, 비주얼 모션·팔레트, 톤, 자막, 아크)로 비교해 유사도를 낸다. 미달이면 축별 델타를
plan 피드백으로 밀어 넣어 다시 만든다. 스타일 값을 코드에 박지 않으므로 다른 레퍼런스는
다른 결과로 수렴한다(예: 느린 컷 레퍼런스는 느린 결과, 빠른 컷은 빠른 결과). 지각 라벨의
판정자 분산에 강인하도록 유사도 metric은 보정돼 있다(설계: [specs/similarity-loop.md](specs/similarity-loop.md)).

## 도구 선택 근거

- **Gemini** - 지각 계층과 이미지 생성용. 멀티모달 모델 하나가 톤, 보이스, 자막 스타일,
  훅을 읽고, 일관된 레퍼런스 아트를 렌더링한다. 키 하나로 분석과 이미지 생성을 덮는다.
- **PySceneDetect / librosa / OpenCV / ffmpeg** - 정형 계층용. 재현 가능하고 값싼 측정
  수치를 만들고, 게이트가 이를 비교한다.
- **pydantic** - 단계를 잇는 스키마용. 생성 백엔드를 바꿔도 소비자가 깨지지 않는다.
- **typer + rich** - CLI용. `run` 일괄 실행과 진행 상황 출력을 담당한다(확인 게이트는 없음).
- **uv** - 설치와 실행용. 바이너리 배포 없이 클론하고 `uv sync` 한 번으로 재현 가능한
  환경을 만든다.

## 테스트

```bash
uv sync --extra dev
uv run pytest -q
```

## 라이선스

MIT. [LICENSE](LICENSE) 참고.

---

# reel-gen-agent (English)

An AI agent CLI that turns a single product into a ready-to-post vertical short
for Instagram Reels, TikTok, and YouTube Shorts. Point it at a product, pick a
reference style, and it produces a one-person short-form clip with a model,
subtitles, and music. It is built for solo creators and small brands doing
short-form promotion and brand awareness.

It fits any product a single person can show worn or used on camera in an indoor
room. Skincare is the top category (serums and ampoules, sunscreen, toner and
moisturizer, cleansers, patches), followed by makeup (cushion and foundation, lip,
eyeshadow, setting spray). It also covers adjacent beauty and wellness
(supplements and diet, clinic treatments, innerwear and athleisure) and extends to
apparel, accessories, bags, shoes, eyewear, and simple home decor props. The
defaults lean toward a female creator and audience, where short-form product PPL
concentrates.

Bring your own API key and start making shorts for free. No timeline editor, no
render farm: describe the product, approve a few steps, get an mp4.

It is a CLI built with `typer` and `rich`. You give it one input and it runs end to
end — input to `ReelProfile` to video — with no human-confirm gates (`run`). If the
input already is a `ReelProfile`, it goes straight to production; if the input has no
clear video purpose, it is rejected.

Under the hood it separates **analysis** from **generation** through a stable JSON
interface, so the generation backend can change without touching the rest. The
core idea: do not hardcode a style. Measure it from references, express it as
reusable data, and drive generation from that data. The same engine that profiles
a reference also scores a generated clip, so references and outputs are judged on
one ruler.

## Status

- `analyze` — implemented. Reference video to a structured `VideoProfile` (JSON).
- `add-reference` — implemented. One URL: download, analyze, evaluate (rubric), save
  profile, catalog. Reference analysis runs analyze + evaluate by default.
- `evaluate` — implemented. Scores a video on the driver rubric (`RubricResult` JSON,
  with an expected-effect note). The same ruler scores references and outputs. See
  [docs/rubric.md](docs/rubric.md).
- `verify` — implemented. Conformance check that the video was built intact as intended
  (hard pass/fail). All references PASS. See [specs/conformance-gate.md](specs/conformance-gate.md).
- `run` / `plan` / `execute` (generation) — implemented (walking skeleton, deepening
  stage by stage). See below.

## How it runs: one-shot run

There are no human-confirm gates or chat sessions (deferred to future work). You give
one input; it builds a `ReelProfile` and pushes straight to production.

- **`reel-gen run <input>`**: input -> `ReelProfile` -> video, in one go. Prints
  progress and returns the mp4 path. With a reference, `--max-iters` re-analyzes the
  output, **compares similarity to the reference, and re-plans/re-generates if it
  falls short** (until similar).
- **`reel-gen plan <input>` / `reel-gen execute <ReelProfile>`**: the same pipeline
  split into two stages that talk only through the `ReelProfile` schema.
- **`reel-gen chat`**: interactive chat mode. Started with no input, it opens with
  "what short-form video do you want to make?" and naturally asks for the purpose,
  product, reference, and vibe (prompt_toolkit). Once it has enough, it builds the
  `ReelProfile` and a key visual, shows a summary, and after **one confirmation**
  runs production. It is conversational intake plus a single confirm (not per-stage
  HITL), so it converges to `run`.

Rules:
- If the input is already a **`ReelProfile` JSON, it skips planning and renders
  directly**.
- If the input has **no clear video purpose, execution is rejected** (exit≠0).
- Otherwise it infers everything else (character, product, environment, music, ...)
  from that purpose.

### Input forms

The positional argument (`<input>`) of `run`/`plan` accepts three forms; the system
detects which one it got.

- **A quoted text brief**: describe the video in natural language, with URLs or local
  paths to the reference video, product, and character embedded. The system extracts
  and classifies each as reference / product / character.
- **A JSON file path**: `generation_input.json` (high-level structured input) or a
  finished `ReelProfile` (skips planning, renders directly).
- **A single asset (image, video, or URL)**: the kind is inferred from extension and
  content (video as reference, image as character/product).

URLs and local paths can be mixed in any form. Text brief example:

```bash
reel-gen run "Make a playful 15s unboxing reel for this product.
product: https://brand.example/serum
reference video: ./reference_video/fast-cut.mp4
character: https://example.com/model.jpg"
```

## Install

This tool ships no prebuilt binary. You clone the repository and install its
dependencies with [uv](https://docs.astral.sh/uv/).

Requires Python 3.10+, `ffmpeg`/`ffprobe` on PATH, and `uv`.

```bash
# 1. Clone
git clone https://github.com/shalomeir/reel-gen-agent.git
cd reel-gen-agent

# 2. ffmpeg (needed for analysis and video assembly)
brew install ffmpeg            # macOS

# 3. Install deps (uv creates .venv and installs the reel-gen command)
uv sync                        # with dev tools: uv sync --extra dev

# 4. Verify
uv run reel-gen --help
```

Activate the virtualenv uv created to call `reel-gen` directly, or wrap each call
with `uv run reel-gen ...`.

```bash
source .venv/bin/activate      # activate once
reel-gen --help                # then call without uv run
```

### Update

You pull the code and re-sync rather than downloading a new binary.

```bash
git pull
uv sync
```

## Environment setup

Copy `.env.example` to `.env` and fill in your own keys.

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | yes | Multimodal analysis + image generation. Get one at [Google AI Studio](https://aistudio.google.com/apikey). |
| `ANTHROPIC_API_KEY` | no | Claude API key for optional storyboard, dialogue script, and tone generation. |
| `GENAI_BACKEND` | no | Backend for multimodal calls. `auto` (default) uses Vertex when its credentials are set, otherwise `GEMINI_API_KEY`. Force with `vertex` or `gemini`. |
| `GEMINI_ANALYSIS_MODEL` | no | Analysis model. Default `gemini-2.5-flash`. |
| `GEMINI_TEXT_MODEL` | no | Gemini text model. Default `gemini-3.1-pro-preview`. |
| `CLAUDE_MODEL` | no | Claude text model. Default `claude-opus-4-8`. |
| `TEXT_MODEL_PRIORITY` | no | Text model priority for concept, hook, and storyboard generation. Defaults to Gemini 3.1 Pro, with Claude Opus as an option. |
| `GEMINI_IMAGE_MODEL` | no | Image model (Nano Banana). Default `gemini-3.1-flash-image-preview`. |
| `VIDEO_PROVIDER` | no | Preferred video provider. `vertex`, `gemini`, or `fal`; blank defaults to `vertex`. |
| `VEO_MODEL`, `VEO_OUTPUT_GCS_URI` | no | Vertex AI image-to-video model and GCS output path. Default `veo-3.1-lite-generate-001`. |
| `GOOGLE_CLOUD_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS` | no | GCP project and service-account JSON path for the Vertex AI lane (video Veo + analysis multimodal). |
| `GEMINI_VEO_MODEL` | no | Gemini API image-to-video fallback model. Default `veo-3.1-lite-generate-preview`. |
| `FAL_KEY`, `FAL_VIDEO_MODEL` | no | Optional fal.ai video provider for Kling O3 Standard/Seedance 2.0 Fast image-to-video. |
| `LYRIA_MODEL` | no | Background music model (generation stage). Defaults to Lyria 3 (Clip, up to 30s); tracks over 30s use Lyria 3 Pro. |
| `ELEVENLABS_API_KEY` | no | Optional voiceover demo. |

The perceptual layer runs on whichever backend `GENAI_BACKEND` selects (Vertex or
`GEMINI_API_KEY`). With neither set, the deterministic layer still produces a
partial profile and the perceptual fields stay empty.

## Usage

Every command takes `--help` to show its arguments and options.

```bash
reel-gen --help                # all commands
reel-gen run --help            # options for one command
```

### Analyze a reference (implemented)

```bash
# Analyze a reference video, print JSON to stdout
reel-gen analyze path/to/video.mp4

# Save to a file and record the source URL
reel-gen analyze path/to/video.mp4 --url "https://..." --out profiles/sample.json

# Deterministic layer only (no API key needed)
reel-gen analyze path/to/video.mp4 --no-gemini

# Ingest a reference from one URL: download + analyze + evaluate + catalog (both by default)
reel-gen add-reference "https://www.youtube.com/shorts/..."
reel-gen add-reference "https://..." --no-evaluate   # analyze only, skip rubric
```

A helper script downloads a reference from YouTube/TikTok into `reference_video/`:

```bash
utils/add-reference.sh "https://www.youtube.com/shorts/..."
```

### Score content effectiveness (implemented)

The driver rubric scores a video on 7 dimensions (D1-D7), each 1 to 5. Hook and
watch-completion form a multiplicative gate; the rest form a weighted additive core,
mapped to 0-100. This is a different axis from style similarity: it asks whether the
clip works as content, not whether it resembles a reference. The same ruler scores
references and outputs.

```bash
# Score a video, print RubricResult (JSON) to stdout
reel-gen evaluate path/to/video.mp4

# Save to a file (evals/ is gitignored)
reel-gen evaluate path/to/video.mp4 --out evals/sample.json
```

Dimensions, weights, formula, and gate thresholds are fixed in
[specs/rubric.md](specs/rubric.md); the rationale is in [docs/rubric.md](docs/rubric.md).

### Verify integrity and fit (implemented)

Checks that the video was built intact as intended (hard pass/fail): media integrity,
template fit, node/merge integrity, volume (LUFS/clipping), subtitle placement and effects,
cut transitions, product representation, and model fit, via deterministic checks and a VLM.
References run only intrinsic checks and all PASS.

```bash
reel-gen verify path/to/video.mp4                  # reference / standalone (intrinsic only)
reel-gen verify final.mp4 --input gen.json --storyboard board.json --manifest run.json
reel-gen verify path/to/video.mp4 --no-vlm         # deterministic checks only
```

A single failing check makes the exit code non-zero (it is a gate). The contract and check
catalog are in [specs/conformance-gate.md](specs/conformance-gate.md).

### Generate a video (implemented, deepening)

One input, pushed end to end with no confirm gates. Rejected if no video purpose.

```bash
# run: input -> ReelProfile -> video, in one go (prints the mp4 path)
reel-gen run "15s unboxing of https://brand.example/serum, character ./model.jpg"  # text brief
reel-gen run generation_input.json               # structured JSON input
reel-gen run ./reference_video/fast-cut.mp4      # a single asset (video) directly

# with a reference: compare similarity, re-plan/re-generate if short (up to 2 iters)
reel-gen run "... reference: ./ref.mp4" --max-iters 2

# give a finished ReelProfile to skip planning and render directly
reel-gen run outputs/<run_id>/plan/ReelProfile-....json

# split into two stages (they talk only through the ReelProfile schema)
reel-gen plan "..."                    # input -> ReelProfile
reel-gen execute outputs/<run_id>/plan/ReelProfile-....json   # ReelProfile -> video

# interactive chat: it asks what it needs, shows a summary + key visual, then confirms
reel-gen chat                          # start from an empty conversation
reel-gen chat "glow serum morning routine reel"   # seed a brief, then keep chatting

# compare: score how close an output is to the reference (non-zero exit on fail)
reel-gen compare --reference ./ref.mp4 --output outputs/<run_id>/final.mp4
reel-gen compare --reference profiles/ref.json --output profiles/gen.json --out sim.json
```

### Render a template directly (`execute`)

A separate command that skips the upstream stages and renders a fully resolved
template JSON straight to video. It is split from `run` so the two inputs are not
confused.

```bash
reel-gen execute storyboard.json
```

The JSON `execute` takes is the same structured format the agent emits at the
storyboard stage (panels, timing, subtitles, music and watermark settings).
Feeding the same JSON back in reproduces the same assembly, so it is handy for
re-rendering after edits and for debugging the assembly step.

Precondition: the character and product catalogs inside the template JSON must
carry **local paths to the already-generated images** that feed video generation.
`execute` checks those paths exist before running and stops with an error if any is
missing, since the video cannot be built without them.

### Command and flag reference

| Command / flag | Behavior |
|---|---|
| `--help` | Help for every command and subcommand (typer default). |
| `reel-gen analyze <video>` | Analyze a reference video into a `VideoProfile` (JSON). |
| `reel-gen add-reference <url>` | Add a reference from a URL (download, analyze, catalog). |
| `reel-gen evaluate <video>` | Score a video on the driver rubric (`RubricResult` JSON, with expected-effect note). |
| `reel-gen verify <video>` | Conformance integrity/fit check (`ConformanceReport` JSON, exit≠0 on fail). |
| `reel-gen run <input>` | input->ReelProfile->video in one go (no confirm gates). A ReelProfile input renders directly; rejected if no purpose. |
| `reel-gen run ... --max-iters <n>` | With a reference, re-plan/re-generate on similarity shortfall (up to n). |
| `reel-gen chat` | Interactive chat mode: asks what it needs, builds ReelProfile + key visual, confirms once, then produces. |
| `reel-gen plan <input>` | input -> `ReelProfile` (profile.json). |
| `reel-gen execute <ReelProfile.json>` | Render a ReelProfile straight to video. Stops if catalog image local paths are missing. |
| `<input>` (`run`/`plan`) | A text brief, a JSON path (generation_input or ReelProfile), or a single asset (image, video, URL). |

## How it works

Two layers feed one profile:

- **Deterministic layer** (local, reproducible): cut distribution, audio dynamics,
  color and brightness. The numeric basis for similarity scoring.
  - `ffprobe` for container metadata
  - PySceneDetect for cut count, length distribution, edit mode
  - librosa for BPM, build-vs-flat dynamics, intro silence
  - OpenCV for dominant palette, brightness, contrast
- **Perceptual layer** (Gemini multimodal): voice tone, overall feel, subtitle
  style, hook, narrative arc.

The generation pipeline expands an input into character/product assets and a
storyboard, freezes it as a `ReelProfile` (plan), then builds the materials (video
clips, voice, bgm, sfx, subtitles) in parallel against the video model's capability
and assembles and verifies them (execute). It runs end to end via `run` with no
confirm gates. Graph structure in [specs/workflows.md](specs/workflows.md), stage
details in [docs/pipeline-design.md](docs/pipeline-design.md).

## Tooling choices

- **Gemini** for the perceptual layer and image generation: one multimodal model
  reads tone, voice, subtitle style, and hook, then renders consistent reference
  art. One key covers analysis and image generation.
- **PySceneDetect / librosa / OpenCV / ffmpeg** for the deterministic layer:
  measured numbers that are reproducible and cheap, which the Gate can compare.
- **pydantic** for the schemas that connect stages, so the generation backend can
  be swapped without breaking consumers.
- **typer + rich** for the CLI: one-shot `run` execution with progress output (no
  confirm gates).
- **uv** for install and execution: no binary distribution, just clone and run
  `uv sync` once for a reproducible environment.

## Test

```bash
uv sync --extra dev
uv run pytest -q
```

## License

MIT. See [LICENSE](LICENSE).
