# reel-gen-agent

> Read this in [English](README.en.md).

제품 하나를 인스타그램 릴스, 틱톡, 유튜브 쇼츠용 세로 숏폼으로 바꿔 주는 AI 에이전트
CLI다. 제품을 가리키고 참고할 스타일을 고르면, 모델과 자막과 음악이 들어간 1인 숏폼
mp4를 만들어 준다. 숏폼 제품 홍보를 돌리는 브랜드를 위한 도구다.
스킨케어, 메이크업 같은 뷰티 제품에서 부터 한 사람이 사용하는 모습을 담을 수 있는 제품이면 의류, 액세서리, 홈 데코 소품까지 넓게 맞는다.

핵심 구조는 PLAN 과 PRODUCTION 과정이 분리 되어 있다는 점이다.
PLAN 과정에서는 스타일을 코드에 박지 않고 주어진 레퍼런스영상에서 영상 스타일을 잡을 수 있고,
영상의 목적, 제품, 그리고 모델을 통해 영상의 스토리보드와 훅을 기획하고 JSON 및 제품 카탈로그,
캐릭터, Key 비주얼을 생성한다.
그리고 PRODUCTION 과정에서는 기획단계에서 생성한 재료들과 JSON으로 정리된 스토리보드 를 가지고,
영상을 생성하고 컷 분리 편집, 음악 생성 및 편집 등이 한번에 이루어진다. 
생성된 결과는 SPEC 에 맞는지 검증 단계, 숏폼으로서 정성적으로 어필할 수 있는지 Evaluate 한다.
이후 최종 영상과 결과 리포트를 생성한다.

## 요구사항

- Python 3.10 이상
- `ffmpeg` / `ffprobe` (PATH에 있어야 한다. 분석과 영상 조립에 쓴다)
- [uv](https://docs.astral.sh/uv/) (설치와 실행)
- **Google API Key 필수** (아래 참고)

### API 키

이 에이전트는 **Google Key 하나만 있으면 실행이 가능하다.** 아래 둘 중 아무거나 하나면 된다.

- **[Google AI Studio](https://aistudio.google.com/apikey)의 `GEMINI_API_KEY`** 하나만 넣으면
  레퍼런스 분석, 스틸 이미지(Nano Banana), 영상(Veo 3.1), 배경음악(Lyria 3),
  나레이션(Gemini TTS)까지 이 키로 전부 생성한다. 별도 GCP 설정 부담이 있는 분에게 추천.
- 아니면 **GCP Vertex AI 자격**(`GOOGLE_CLOUD_PROJECT` + 서비스계정 JSON)만 채워도 된다. 같은 Veo/Lyria/분석이 Vertex 레인으로 돌아 Google Cloud 크레딧을 쓴다.
- 둘 다 채우면 `GENAI_BACKEND=auto`가 Vertex를 우선한다(`gemini`/`vertex`로 강제 가능).

Google 외에 아래 의 API 키를 더 넣으면 특정 부분의 품질이 눈에 띄게 올라간다.

| 선택 키 | 좋아지는 점 |
|---|---|
| `FAL_KEY` (fal.ai) | 영상을 Kling O3로 생성해 기본 Veo보다 영상 퀄리티가 확실히 좋아진다. |
| `ELEVENLABS_API_KEY` | 나레이션 음성이 더 자연스러워진다(나레이션 방식일 때만). 없으면 Gemini TTS로 내려간다. |
| `FIRECRAWL_API_KEY` | 레퍼런스 URL(쇼핑몰 상품 페이지 등)에서 제품 인식 성능이 확연히 좋아진다. |
| `ANTHROPIC_API_KEY` | 스토리보드, 대사, 톤 생성 텍스트 레인을 Claude Opus로 돌릴 수 있다. |

전체 변수 목록과 기본값, 발급처는 [`.env.example`](.env.example)에 있다.

## 설치

빌드된 바이너리를 배포하지 않는다. 저장소를 클론하고 `uv`로 의존성을 깔아 쓴다.

```bash
# 1. 클론
git clone https://github.com/shalomeir/reel-gen-agent.git
cd reel-gen-agent

# 2. ffmpeg (macOS 기준)
brew install ffmpeg

# 3. 의존성 설치 (uv가 .venv를 만들고 reel-gen 명령을 깐다)
uv sync                        # 개발 도구까지: uv sync --extra dev

# 4. 환경 파일 준비
cp .env.example .env           # .env를 열어 API 키를 채운다
# GEMINI_API_KEY=...           # Google AI Studio 키 하나면 시작 가능

# 5. 확인
uv run reel-gen --help
```

가상환경을 활성화하면 `reel-gen`을 바로 부를 수 있고, 아니면 `uv run reel-gen ...`으로
매번 감싸 실행한다. 업데이트는 `git pull && uv sync`.

```bash
source .venv/bin/activate      # 한 번 활성화하면
reel-gen --help                # uv run 없이 호출
```

## 사용법

명령 목록은 `reel-gen --help`로 본다. 각 명령의 옵션은 `reel-gen <명령> --help`.

![reel-gen --help](docs/capture/reel-gen-cli-help.png)

### 영상 생성: `run`

입력 하나를 받아 `ReelProfile`을 만들고 영상까지 한 번에 민다. 확인 게이트(HITL)는
없고, 영상 목적이 명확하지 않으면 거절한다. 클론한 위치에서 샘플 입력으로 바로 돌릴 수
있다.

```bash
# 동봉된 샘플 입력으로 바로 실행
reel-gen run ./demo/sample_input_1.json

# 자연어 브리프로 실행 (URL·로컬 경로를 섞어 넣으면 레퍼런스/제품/캐릭터로 분류한다)
reel-gen run "이 제품으로 발랄한 15초 언박싱 릴 만들어줘.
제품: https://brand.example/serum
레퍼런스 영상: ./reference_video/fast-cut.mp4
캐릭터: https://example.com/model.jpg"
```

입력은 세 가지 형태를 받는다. 텍스트 브리프, JSON 파일 경로(`generation_input.json` 또는
완성된 `ReelProfile`), 단일 에셋(이미지·영상·URL). 무엇이 들어왔는지는 시스템이 판별한다.
레퍼런스를 함께 주면 `--max-iters`로 생성물을 다시 분석해 유사도를 비교하고, 미달이면
축별 델타를 피드백으로 재계획·재생성한다.

### 대화형 챗 모드: `chat`

물어보며 입력을 채우고, 요약과 대표 이미지를 확인받은 뒤 생성한다. 단계별 게이트가 아니라
입력 수집과 최종 확인 한 번이라, 결국 `run`으로 수렴한다.

```bash
reel-gen chat                          # 빈 상태에서 대화로 시작
reel-gen chat "글로우 세럼 아침 루틴 릴"   # 시작 브리프를 주고 이어서 대화
```

![reel-gen chat](docs/capture/reel-gen-cahtmode_ing.png)

### 레퍼런스 분석과 채점

```bash
# 레퍼런스 영상을 VideoProfile(JSON)로 분석 (로컬 경로 또는 URL)
reel-gen analyze path/to/video.mp4
reel-gen analyze path/to/video.mp4 --no-gemini   # 정형 계층만, API 키 불필요

# 드라이버 Rubric으로 콘텐츠 효과성 채점 (레퍼런스와 생성물에 같은 자를 댄다)
reel-gen evaluate path/to/video.mp4
```

`analyze`는 컷 분포, 오디오 다이내믹, 색·밝기 같은 정형 측정에 Gemini 지각 라벨(톤, 느낌,
자막 스타일, 훅)을 더한다. `evaluate`는 후크·완시청을 곱셈 게이트로, 나머지를 가중합으로
묶어 0~100점을 낸다. 닮았는지가 아니라 콘텐츠로서 먹히는지를 본다.

## 출력물

결과는 `./outputs/<run_id>/` 아래에 쌓인다. `run_id`는 `컨셉축약-생성일시` 형태다.

```
outputs/<run_id>/
├── plan/
│   ├── ReelProfile-<run_id>.json   # 기획 동결본 (핵심, rerun 입력 가능하게 해줌)
│   └── ...                         # 캐릭터·제품·앵커 스틸 등 기획 산출물
├── execute/                        # production 중간물 (스틸, 컷별 영상 클립, 오디오)
├── final.mp4                       # 최종 영상
├── report.md                       # 회차 리포트 (사용 모델, 노드 흐름, 채점, 예상 비용)
├── upload.md                       # 업로드 킷 (제목, 캡션, 해시태그)
└── run.json                        # RunManifest (실행 기록, 적용된 폴백)
```

- **`plan/ReelProfile-<run_id>.json`**: 기획의 동결 합본이다. 컨셉, 스타일, 에셋, 스토리보드,
  후크, 생산 의도를 한 파일에 담은 이식 가능한 창작 의도다. 같은 ReelProfile은 유사한
  영상을 만든다.
- **`final.mp4` / `report.md` / `upload.md`**: 최종 영상, 회차 리포트, 올릴 때 쓰는
  업로드 킷. run 루트에 함께 떨어진다.
- **`execute/`**: production이 만든 앵커 스틸, 컷별 영상 클립, 오디오 같은 중간물이다.

이미 만든 `ReelProfile`이 있으면 앞단을 다시 돌릴 필요가 없다.

```bash
# plan을 건너뛰고 ReelProfile을 곧장 영상으로
reel-gen execute outputs/<run_id>/plan/ReelProfile-<run_id>.json

# 같은 제품·캐릭터 정체성은 고정하고, 훅부터 서사·음악 기획 파트만 새로 굴려 다른 1편을 새 폴더에 만든다
reel-gen rerun outputs/<run_id>/plan/ReelProfile-<run_id>.json
```

`rerun`은 정체성을 유지한 채 훅·스토리보드·음악만 다시 생성해 새로운 영상 결과를 만든다.

### 생성 시간과 비용

한 편에 대략 10분(분석 약 30초, plan 약 2분, execute 약 6분), 15초 숏폼 기준 대략
**$3~$4**다(스틸, BGM, 나레이션 포함). 실제 청구가 아니라 공개 단가 기준 예상치이고,
회차 리포트에 모델별 예상 비용이 함께 나온다.

## 더 읽을 문서

- [analysis.md](analysis.md): 개발 과정과 기술 분석. plan/production 구현, LangGraph 구조,
  모델 선택 기록을 잇는 지도.
- [retro.md](retro.md): 회고. 가정, 막힌 점, 한계, 더 있었으면 개선할 것.
- [specs/project-brief.md](specs/project-brief.md): 제품 의도와 성공 기준(루트 비전).
- [specs/workflows.md](specs/workflows.md): **LangGraph StateGraph 구조.** 이 에이전트의 기본
  뼈대(두 페이즈, 노드, 게이트)를 정의한 정본.
- [specs/ai-model-records.md](specs/ai-model-records.md): 용도별 모델 선택과 그 근거.
- [docs/ToolnModels.md](docs/ToolnModels.md): 어떤 모델, API, 라이브러리를 왜 골라 썼는지.
- [docs/hook-insight.md](docs/hook-insight.md): 훅 생성 로직의 참고 자료.
- [docs/rubric.md](docs/rubric.md): `evaluate` 채점 기준의 배경.
- 그 밖에 [specs/prd.md](specs/prd.md)(요구사항), [specs/trd.md](specs/trd.md)(기술 계약),
  [specs/hook-generator.md](specs/hook-generator.md)(훅 계약),
  [specs/information-schema.md](specs/information-schema.md)(스키마),
  [specs/product-design.md](specs/product-design.md)(CLI/UX).

## 라이선스

MIT. [LICENSE](LICENSE) 참고.
