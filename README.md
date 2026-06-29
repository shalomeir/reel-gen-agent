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
팜도 없다. 제품을 설명하고, 몇 단계를 승인하면, mp4가 나온다.

내부에서는 안정적인 JSON 인터페이스를 통해 **분석**과 **생성**을 분리한다. 그래서 생성
백엔드를 바꿔도 나머지를 건드리지 않는다. 핵심 발상은 스타일을 하드코딩하지 않는 것이다.
레퍼런스에서 측정하고, 재사용 가능한 데이터로 표현하고, 그 데이터로 생성을 끌고 간다.
레퍼런스를 프로파일링하는 엔진이 생성된 클립도 채점하므로, 레퍼런스와 출력이 같은 잣대로
판단된다.

## 상태

- `analyze` — 구현됨. 레퍼런스 영상을 구조화된 `VideoProfile`(JSON)로.
- `generate` — 설계됨, 아직 구현 전. [docs/pipeline-design.md](docs/pipeline-design.md) 참고.

## 동작 방식

두 계층이 하나의 프로파일을 만든다.

- **정형 계층**(로컬, 재현 가능): 컷 분포, 오디오 다이내믹, 색과 밝기. 유사도 채점의
  수치 근거다.
  - 컨테이너 메타데이터는 `ffprobe`
  - 컷 수, 길이 분포, 편집 모드는 PySceneDetect
  - BPM, 빌드 대 플랫 다이내믹, 인트로 무음은 librosa
  - 주요 팔레트, 밝기, 대비는 OpenCV
- **지각 계층**(Gemini 멀티모달): 보이스 톤, 전체 느낌, 자막 스타일, 훅, 내러티브 아크.

생성 파이프라인(설계됨)은 `generation_input.json`을 에셋 바이블(캐릭터, 제품 레퍼런스
이미지)로, 분석된 컷 리듬을 씨앗으로 삼은 패널별 타이밍의 스토리보드 JSON으로, 그리고
마지막으로 image-to-video와 ffmpeg를 거친 조립된 영상으로 바꾼다. 중요한 단계마다 사람이
확인하고 수정하는 게이트가 걸리고, 모든 게이트를 통과시키는 비인터랙티브 런 모드도 있다.
자세한 내용은 [docs/pipeline-design.md](docs/pipeline-design.md)에 있다.

## 설치

Python 3.10+와 `ffmpeg`/`ffprobe`가 PATH에 있어야 한다.

```bash
brew install ffmpeg            # macOS
pip install -e .               # `reel-gen` 명령을 설치
# 또는: pip install -r requirements.txt
```

## 환경 설정

`.env.example`을 `.env`로 복사하고 자기 키를 채운다.

```bash
cp .env.example .env
```

| 변수 | 필수 | 용도 |
|---|---|---|
| `GEMINI_API_KEY` | 예 | 멀티모달 분석 + 이미지 생성. [Google AI Studio](https://aistudio.google.com/apikey)에서 발급. |
| `GEMINI_ANALYSIS_MODEL` | 아니오 | 분석 모델. 기본 `gemini-2.5-flash`. |
| `GEMINI_IMAGE_MODEL` | 아니오 | 이미지 모델. 기본 `gemini-3.1-flash-image`. |
| `VEO_MODEL` | 아니오 | image-to-video 모델(생성 단계). |
| `LYRIA_MODEL` | 아니오 | 배경 음악 모델(생성 단계). |
| `ELEVENLABS_API_KEY` | 아니오 | 선택 보이스오버 데모. |

분석기는 `GEMINI_API_KEY`만으로 돈다. 키가 없으면 정형 계층이 부분 프로파일을 만들고,
지각 필드는 비워 둔다.

## 실행

```bash
# 레퍼런스 영상을 분석하고 JSON을 stdout으로 출력
reel-gen analyze path/to/video.mp4

# 파일로 저장하고 출처 URL 기록
reel-gen analyze path/to/video.mp4 --url "https://..." --out profiles/sample.json

# 정형 계층만 (API 키 불필요)
reel-gen analyze path/to/video.mp4 --no-gemini
```

유튜브/틱톡에서 레퍼런스를 `reference_video/`로 받아오는 헬퍼 스크립트:

```bash
utils/add-reference.sh "https://www.youtube.com/shorts/..."
```

## 테스트

```bash
pip install -e ".[dev]"
pytest -q
```

## 도구 선택 근거

- **Gemini** — 지각 계층과 이미지 생성용. 멀티모달 모델 하나가 톤, 보이스, 자막 스타일,
  훅을 읽고, 일관된 레퍼런스 아트를 렌더링한다. 키 하나로 분석과 이미지 생성을 덮는다.
- **PySceneDetect / librosa / OpenCV / ffmpeg** — 정형 계층용. 재현 가능하고 값싼 측정
  수치를 만들고, 게이트가 이를 비교한다.
- **pydantic** — 단계를 잇는 스키마용. 생성 백엔드를 바꿔도 소비자가 깨지지 않는다.
- **typer + rich** — 사람이 확인하는 게이트를 가진 인프로세스 CLI용.

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

Under the hood it separates **analysis** from **generation** through a stable JSON
interface, so the generation backend can change without touching the rest. The
core idea: do not hardcode a style. Measure it from references, express it as
reusable data, and drive generation from that data. The same engine that profiles
a reference also scores a generated clip, so references and outputs are judged on
one ruler.

## Status

- `analyze` — implemented. Reference video to a structured `VideoProfile` (JSON).
- `generate` — designed, not yet implemented. See [docs/pipeline-design.md](docs/pipeline-design.md).

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

The generation pipeline (designed) turns a `generation_input.json` into an asset
bible (character and product reference images), a storyboard JSON with per-panel
timing seeded from the analyzed cut rhythm, and finally an assembled video via
image-to-video plus ffmpeg. Every important step is gated for human confirm and
edit, with a non-interactive run mode that passes all gates. Details in
[docs/pipeline-design.md](docs/pipeline-design.md).

## Install

Requires Python 3.10+ and `ffmpeg`/`ffprobe` on PATH.

```bash
brew install ffmpeg            # macOS
pip install -e .               # installs the `reel-gen` command
# or: pip install -r requirements.txt
```

## Environment setup

Copy `.env.example` to `.env` and fill in your own keys.

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | yes | Multimodal analysis + image generation. Get one at [Google AI Studio](https://aistudio.google.com/apikey). |
| `GEMINI_ANALYSIS_MODEL` | no | Analysis model. Default `gemini-2.5-flash`. |
| `GEMINI_IMAGE_MODEL` | no | Image model. Default `gemini-3.1-flash-image`. |
| `VEO_MODEL` | no | Image-to-video model (generation stage). |
| `LYRIA_MODEL` | no | Background music model (generation stage). |
| `ELEVENLABS_API_KEY` | no | Optional voiceover demo. |

The analyzer runs with `GEMINI_API_KEY` alone. Without it, the deterministic layer
still produces a partial profile and the perceptual fields stay empty.

## Run

```bash
# Analyze a reference video, print JSON to stdout
reel-gen analyze path/to/video.mp4

# Save to a file and record the source URL
reel-gen analyze path/to/video.mp4 --url "https://..." --out profiles/sample.json

# Deterministic layer only (no API key needed)
reel-gen analyze path/to/video.mp4 --no-gemini
```

A helper script downloads a reference from YouTube/TikTok into `reference_video/`:

```bash
utils/add-reference.sh "https://www.youtube.com/shorts/..."
```

## Test

```bash
pip install -e ".[dev]"
pytest -q
```

## Tooling choices

- **Gemini** for the perceptual layer and image generation: one multimodal model
  reads tone, voice, subtitle style, and hook, then renders consistent reference
  art. One key covers analysis and image generation.
- **PySceneDetect / librosa / OpenCV / ffmpeg** for the deterministic layer:
  measured numbers that are reproducible and cheap, which the Gate can compare.
- **pydantic** for the schemas that connect stages, so the generation backend can
  be swapped without breaking consumers.
- **typer + rich** for an in-process CLI with human-in-the-loop confirm gates.

## License

MIT. See [LICENSE](LICENSE).
