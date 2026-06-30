# 제품 설계: 챗봇형 CLI와 입력 형식

상태: 설계. 이 문서는 CLI의 사용자 경험(모드, 게이트, 입력 형식)을 정리한다. 생성 단계
내부의 계약은 [pipeline-design.md](../docs/pipeline-design.md)에, 사용자용 요약은
[../README.md](../README.md)에 있다. 셋이 어긋나면 이 문서가 UX 기준이다.

## 한 줄 요약

`typer`와 `rich`로 만든 챗봇형 CLI다. 같은 생성 파이프라인을 대화형(챗 모드)으로도,
한 번에 도는 비대화(런 모드)로도 돌릴 수 있다. 두 모드는 게이트(사람 확인 지점)를 어떻게
다루느냐만 다르다. 여기에, 이미 완성된 템플릿 JSON을 그대로 영상으로 뽑는 직행 명령
(`execute`)을 따로 둔다.

## 두 가지 모드

생성 파이프라인은 컨셉, 에셋 바이블, 스토리보드, 영상 단계마다 게이트를 둔다. 게이트는
세 가지로 동작한다(자세한 건 [pipeline-design.md](../docs/pipeline-design.md)의 "휴먼 인 더 루프
게이트").

- **챗 모드** (`reel-gen chat`): 대화형 챗봇으로 띄운다. 게이트마다 멈춰 결과를 보여주고,
  사용자가 확인하거나 수정한 뒤 다음으로 넘어간다. 기본값은 HITL(사람 개입) 켜짐.
- **런 모드** (`reel-gen run <입력>`): 입력 하나로 끝까지 한 번에 돌린다. 멈추지 않고 모든
  게이트를 자동 통과하며, 진행 상황을 출력한 뒤 mp4 경로를 돌려준다. 비대화라 스크립트나
  CI에 건다. 런 모드에서는 HITL이 불가능하다.

### 게이트 제어 플래그

- `--help`: 모든 명령과 하위 명령의 도움말(typer 기본).
- `-y`, `--yes`: 챗 모드를 유지하되 모든 게이트를 자동 승인한다. 챗 UI는 그대로지만 멈추지
  않는다. "챗 모드인데 HITL은 끄고 싶다"를 위한 플래그다.
- `--force-step-pass <step>`: 특정 게이트 하나만 건너뛴다(반복 지정 가능).
  `<step>`은 `concept`, `asset_bible`, `storyboard`, `video`.

`reel-gen chat --yes`와 `reel-gen run`의 차이: 둘 다 멈추지 않지만, 전자는 챗 REPL UI를
유지하고 후자는 순수 비대화로 진행 상황만 출력하고 종료한다. 런 모드가 스크립트와 CI의
기본 진입점이다.

### 영상 단계 뒤 게이트 흐름

영상 단계 뒤에 **verify**(conformance, 하드 pass/fail)가 먼저 돌고, 통과하면 **evaluate**
(rubric, 소프트 0~100점 + 기대 효과 서술)가 돈다. verify가 fail이면 evaluate로 가지 않고,
문제 노드를 다시 돌려 verify가 통과할 때까지 반복한다. 무한 루프를 막으려고 최대 iteration
count를 둔다(상한에 닿으면 마지막 리포트와 함께 실패로 종료). 자세한 동작은 아래
"분석·검증·평가 명령"과 [trd.md](trd.md) "테스트 전략"에 있다.

## 입력 형식

`chat`과 `run`의 위치 인자(`<입력>`)는 세 가지 형태를 받는다. 무엇이 들어왔는지는 시스템이
판별한다. 기본 원칙은 이미지, 영상, URL을 모두 입력으로 받는 것이다.

1. **`generation_input.json` 파일 경로**: 제품, 스타일, 내러티브 등이 담긴 상위 구조화 입력
   (`GenerationInput`, 스키마는 `src/reel_gen_agent/generate/schema.py`). 컨셉부터 전체
   파이프라인을 탄다. (이미 완성된 템플릿/스토리보드 JSON을 그대로 영상으로 뽑는 직행 경로는
   `chat`/`run`이 아니라 별도 명령 `execute`다. 아래 "직행 실행 명령" 참고.)
2. **따옴표로 감싼 텍스트 브리프**: 만들고 싶은 영상을 자연어로 적되, 그 안에 참고할 영상,
   제품, 캐릭터의 URL이나 로컬 경로를 섞어 넣는다. 컨셉 단계가 텍스트를 읽어 에셋을 뽑고
   각각을 레퍼런스 영상 / 제품 / 캐릭터 이미지로 분류한 뒤 `generation_input`을 채운다.
3. **단일 에셋(이미지·영상·URL)**: 이미지나 영상 파일 경로, 혹은 URL 하나를 바로 넘긴다.
   확장자와 내용으로 종류를 추정하고(영상은 레퍼런스, 이미지는 캐릭터/제품), 나머지 필드는
   기본값이나 이어지는 대화로 채운다.

URL과 로컬 경로는 어느 형태에서든 섞어 쓸 수 있다.

### 판별 규칙(구현 지침)

- `chat`/`run`의 인자가 존재하는 `.json` 파일을 가리키면 → 형태 1(`GenerationInput`)로 보고
  전체 파이프라인을 탄다. (완성된 `Storyboard` JSON 직행은 `chat`/`run`이 아니라 `execute`
  명령으로 분리했다. 아래 "직행 실행 명령".)
- 인자가 존재하는 파일 경로이거나 단일 URL이고, 공백 없는 단일 토큰이면 → 형태 3(단일 에셋).
  미디어 종류는 확장자(`.mp4`, `.mov`는 영상; `.jpg`, `.png`, `.webp`는 이미지)와 필요 시
  내용으로 추정한다.
- 그 밖에(여러 토큰을 담은 자연어 문자열) → 형태 2(텍스트 브리프). 문자열에서 URL과 경로를
  추출해 각 에셋의 역할을 분류하고, 남은 자연어는 컨셉/내러티브로 쓴다.
- 에셋 역할 분류는 1차로 텍스트의 라벨("제품:", "레퍼런스 영상:", "캐릭터:" 등)을 따르고,
  라벨이 없으면 미디어 종류로 추정한다(영상→레퍼런스, 인물 이미지→캐릭터, 제품 이미지/URL→제품).
- 모호하거나 빠진 필드는 챗 모드에서 사용자에게 되묻고, 런 모드에서는 기본값으로 채운다.

### 예시

텍스트 브리프(런 모드):

```bash
reel-gen run "이 제품으로 발랄한 15초 언박싱 릴 만들어줘.
제품: https://brand.example/serum
레퍼런스 영상: ./reference_video/fast-cut.mp4
캐릭터: https://example.com/model.jpg"
```

단일 에셋(영상 하나를 레퍼런스로):

```bash
reel-gen run ./reference_video/fast-cut.mp4
```

챗 모드를 텍스트 브리프로 시작:

```bash
reel-gen chat "이 선크림으로 데일리 루틴 릴, 레퍼런스 ./ref.mp4"
```

## 분석·검증·평가 명령 (analyze / verify / evaluate)

세 명령은 생성과 독립으로 단독 실행할 수 있고, 동시에 생성 그래프 안에서 노드로 재사용한다.
같은 코드를 레퍼런스와 생성물에 똑같이 댄다.

### analyze - 영상 분석 (URL 또는 로컬 경로 -> VideoProfile)

```bash
reel-gen analyze ./reference_video/clip.mp4          # 로컬 파일
reel-gen analyze "https://www.youtube.com/shorts/…"  # URL: 먼저 내려받고 분석
reel-gen analyze "https://instagram.com/…" --cookies-from-browser chrome
reel-gen analyze ./clip.mp4 --out profiles/clip.json --no-gemini
```

입력이 `http://`나 `https://`로 시작하면 URL로 보고 먼저 내려받은 뒤 분석한다(다운로드는
`utils/add-reference.sh`의 yt-dlp에 위임). 그 밖에는 로컬 경로다. 산출물은 `VideoProfile`
JSON 하나다.

역할 셋(그래프에서 재사용):

1. **레퍼런스 분석**: 참고 영상을 넣을 때 프로필을 뽑는다.
2. **생성 앞단 입력**: "이 영상처럼 만들어줘"라고 부탁할 때, 레퍼런스에서 패턴, 흐름, 포맷을
   읽어 비슷한 결의 영상을 만들도록 `generation_input`을 시딩한다.
3. **최종 비교 검증**: 만들어진 최종 영상을 다시 분석해 템플릿 프로필과 같게 나왔는지
   대조한다(스타일 유사도).

`add-reference`와의 차이: `analyze`는 분석만 한다. `add-reference`는 URL을 받아 다운로드,
분석에 더해 `reference_video/list.md` 카탈로그 항목까지 추가하는 큐레이션 명령이다.

### verify - 기술 완성도 검증 (하드 pass/fail)

```bash
reel-gen verify ./outputs/run/final.mp4 --input gen.json --storyboard board.json --manifest run.json
```

영상이 테크니컬하게 온전히 완성됐는지 본다. 역할:

- **생성 그래프의 "영상 결과물 확인" 노드 게이트**. 여기서 pass가 안 되면 문제 노드를 다시
  돌려 verify가 통과할 때까지 반복한다. 무한 루프를 막으려고 최대 iteration count를 둔다.
- 별도 명령으로도 돌릴 수 있으나 단독 사용은 드물다(주로 그래프 안 게이트로 쓰인다).

계약과 체크 카탈로그는 [conformance-gate.md](conformance-gate.md).

### evaluate - 최종 rubric 평가 (verify 직후)

```bash
reel-gen evaluate ./outputs/run/final.mp4
```

verify를 통과한 최종 결과를 정성 평가한다. 역할:

- 드라이버 rubric 점수에 더해, **이 영상으로 기대되는 바이럴 또는 효과를 대략 서술**한다.
- 레퍼런스 영상에는 `analyze`와 함께 실행한다(레퍼런스라면 보통 분석과 평가를 같이 돌려
  기준선을 잡는다).

계약은 [rubric.md](rubric.md).

## 직행 실행 명령 (`execute`)

생성 파이프라인은 컨셉 → 에셋 바이블 → 스토리보드 → 영상 순으로 흐른다. 그런데 입력 JSON이
이미 완성된 스토리보드(에이전트가 스토리보드 단계에서 내놓는 `Storyboard`와 같은 정형 포맷)면,
앞 단계는 더 계산할 게 없다. 이걸 그대로 주입해 곧장 영상만 뽑는 별도 명령이 `execute`다.

```bash
reel-gen execute storyboard.json
```

`run`과 분리한 이유: `run`은 상위 입력(생성 입력·텍스트 브리프·단일 에셋)을 받아 파이프라인을
끝까지 돌리는 반면, `execute`는 정형화된 중간 산출물을 받아 조립만 한다. 입력 성격이 다르고
헷갈리기 쉬워 명령을 가른다.

이게 의미 있는 이유:

- **재실행과 미세 수정**: 챗 모드에서 한 번 만든 스토리보드 JSON을 저장해 두면, 자막 한 줄이나
  타이밍만 손본 뒤 같은 JSON을 `execute`에 다시 넣어 영상만 새로 뽑는다. 비싼 앞 단계를
  반복하지 않는다.
- **디버그**: 포맷이 매우 정형화돼 있고 같은 JSON이 같은 조립을 재현하므로, 조립 단계만 떼어
  재현·디버그하기 좋다.

### 전제 조건과 검증

`execute`가 받는 템플릿 JSON 안의 캐릭터와 제품 카탈로그에는, 영상 생성에 들어갈 **이미 생성된
이미지의 로컬 경로**가 들어 있어야 한다(에이전트가 에셋 바이블 단계에서 이미 만들어 둔 그
이미지들). `execute`는 다음을 따른다.

- 실행 전에 카탈로그(캐릭터·제품)의 이미지 로컬 경로가 실제로 존재하는지 확인한다.
- 하나라도 없으면 영상을 만들 수 없으므로, 누락된 경로를 알려 주고 그 자리에서 실행을 멈춘다
  (에러 종료). 자동 재생성으로 메우지 않는다. 직행은 "이미 만들어 둔 에셋으로 조립만 한다"는
  계약이기 때문이다.
- 그 밖에 조립에 필요한 항목(패널 타이밍, 자막, 음악·워터마크 설정)도 JSON 안에 있어야 한다.

## 설치와 실행(요약)

빌드된 바이너리를 배포하지 않는다. 저장소를 클론하고 [uv](https://docs.astral.sh/uv/)로
의존성을 깐다. 업데이트는 `git pull` 후 `uv sync`. 자세한 건 [../README.md](../README.md)
"설치".

## 연결 문서

- 생성 단계 내부 계약과 스키마: [pipeline-design.md](../docs/pipeline-design.md)
- 사용자용 요약과 명령/옵션 표: [../README.md](../README.md)
