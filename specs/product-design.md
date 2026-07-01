# 제품 설계: CLI와 입력 형식

상태: 설계. 이 문서는 CLI의 사용자 경험(입력 형식, 실행)을 정리한다. 생성 단계
내부의 계약은 [pipeline-design.md](../docs/pipeline-design.md)에, 사용자용 요약은
[../README.md](../README.md)에 있다. 셋이 어긋나면 이 문서가 UX 기준이다.

> **개정(2026-07-01): 단계별 HITL 게이트 제거, run 일괄 + chat 대화형 인테이크.** 초기 설계의
> 단계별 사람 확인 게이트(ask/pass)는 **제거**한다. 기본은 **입력 하나를 받아 ReelProfile을
> 만들고 곧장 production까지 밀어붙이는 `run` 일괄 실행**이다. 규칙: (1) 입력이 이미
> `ReelProfile` JSON이면 계획을 건너뛰고 **바로 production**. (2) 입력(텍스트/JSON, 로컬 경로·URL
> 포함 가능)에 **영상 목적이 명확하지 않으면 거절**(exit≠0). (3) 목적이 있으면 그 목적만으로
> 나머지(캐릭터·제품·환경·음악)를 추론해 채운다.
>
> `chat`은 **대화형 인테이크**로 구현했다(prompt_toolkit). 입력 없이 시작하면 "어떤 숏폼
> 영상을 만들까요?"로 열어 목적·제품·레퍼런스·바이브를 자연스럽게 물어(LLM 주도, 한 번에
> 하나씩) 채우고, 충분해지면 ReelProfile+대표 이미지(key_visual)를 만들어 요약을 보여준 뒤
> **한 번 확인받고** production으로 간다. 즉 단계별 HITL이 아니라 입력 수집 + 최종 확인 1회로,
> 결국 run으로 수렴한다. 아래 본문의 "단계별 게이트/ask 모드" 서술은 이 개정으로 대체된다.

## 한 줄 요약

`typer`와 `rich`로 만든 챗봇형 CLI다. 시스템은 **두 구간으로 완전히 분리**된다. `plan`은
입력에서 기획을 펼쳐 `ReelProfile`(profile.json)을 산출하고, `execute`는 그 ReelProfile만
받아 영상을 만든다. 둘은 ReelProfile 스키마로만 통신한다. `run`은 둘을 한 번에 잇고,
`chat`은 한 세션에서 대화형으로 plan을 돌린 뒤 사용자가 확인하면 execute로 넘어간다.
구간 분리는 내부 구조이고, 사용자에게는 run/chat이 한 번에 도는 경험으로 보인다.

## 두 구간: plan과 execute

시스템은 두 구간으로 완전히 분리된다. 경계는 `ReelProfile`(profile.json) 하나다. 구간별
노드와 흐름은 [workflows.md](workflows.md)가 정본이다(plan=Planning 페이즈, execute=Production
페이즈).

- **`reel-gen plan <입력>`**: Planning 페이즈를 돈다. 입력(영상 목적 + 캐릭터/제품 + 선택
  레퍼런스)에서 컨셉, 후크, 에셋, 환경, 스토리보드, 대사·자막·음악 정의를 펼쳐
  `ReelProfile-{핵심컨셉}-{생성일시}.json`을 산출한다. 챗 모드면 산출한 ReelProfile을 확인받고,
  수정 요청이 있으면 반영해 다시 만든다.
- **`reel-gen execute <ReelProfile.json>`**: Production 페이즈를 돈다. ReelProfile만 받아
  ProductionPlan 해소, 재료 병렬 생성, 조립, verify 루프, describe, evaluate, report까지
  돌려 `outputs/<run_id>/`에 영상과 산출물을 남긴다. 이미 생성된 에셋·클립이 있으면
  재생성을 건너뛴다(조립만). 기존 "storyboard 직행" execute를 이 명령이 흡수한다.
- **`reel-gen rerun <ReelProfile.json>`**: 정체성은 고정하고 Planning의 narrative만 다시
  전개(style부터 재생성)한 새 ReelProfile을 만든 뒤 Production까지 돌린다. "같은 정체성,
  다른 어프로치"용이다. 자세한 계약은 아래 "rerun 명령" 절과 [replan.md](replan.md).

## 한 번에: run과 chat

같은 두 구간을 한 흐름으로 잇는 진입점이다. 단계별 사람 확인 게이트는 없다(개정 노트 참고).
사람 확인은 `chat`이 그래프 밖에서 한 번, 최종 확인·수정 루프로 넣는다.

- **챗 모드** (`reel-gen chat [시드]`): 대화형 챗봇으로 띄운다. 입력 없이 시작하면 목적·제품·
  레퍼런스·바이브를 자연스럽게 물어(LLM 주도, 한 번에 하나씩) 채운다. 충분해지면 ReelProfile과
  대표 이미지(key_visual)를 만들어 요약을 보여주고, 사용자가 확인(y)하면 같은 세션에서 execute로
  넘어간다. 확인 대신 수정 요청을 주면 반영해 다시 만들어 보여준다(확인할 때까지 반복). 즉 단계별
  게이트가 아니라 입력 수집 + 최종 확인·수정 루프다. 내부적으로는 plan과 execute가 분리돼 있다.
- **런 모드** (`reel-gen run <입력>`): 입력 하나로 plan부터 execute까지 끝까지 한 번에 돌린다.
  멈추지 않고 진행 상황을 출력한 뒤 mp4 경로를 돌려준다. 비대화라 스크립트나 CI에 건다.
  레퍼런스가 있고 `--max-iters>1`이면 생성물을 다시 analyze해 유사도가 임계 미만일 때 재계획·
  재생성한다(specs/similarity-loop.md).

`reel-gen chat`과 `reel-gen run`의 차이: 전자는 챗 REPL로 입력을 채우고 최종 확인·수정 루프를
돌고, 후자는 순수 비대화로 입력 하나를 받아 끝까지 밀어붙인다. 런 모드가 스크립트와 CI의
기본 진입점이다.

### 영상 단계 뒤 흐름

영상 단계 뒤에 **verify**(conformance)가 먼저 돌고, 이어 **evaluate**(rubric, 소프트 0~100점
+ 기대 효과 서술)가 돈다. 단독 CLI `verify`는 하드 pass/fail(fail이면 exit≠0)이고, 그래프
안에서도 verify는 하드 게이트다: 교정 가능한 fail이면 교정 파라미터를 실어 문제 노드로 되돌려
재생성하고(최대 3회), 통과하거나 소진하면 다음으로 진행하며 미해결 fail을 report에 남긴다.
이번 범위의 교정은 loudness 하나이고, visuals 등 다른 축은 같은 틀에 향후 추가한다. 자세한
동작은 아래 "분석·검증·평가·비교 명령"과 [testing-strategy.md](testing-strategy.md)에 있다.

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

## 분석·검증·평가·비교 명령 (analyze / verify / evaluate / compare)

네 명령은 생성과 독립으로 단독 실행할 수 있고, 동시에 생성 그래프 안에서 노드로 재사용한다.
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

`add-reference`와의 차이: `analyze`는 분석만 한다. `add-reference`는 URL을 받아 레퍼런스를
들이는 큐레이션 명령으로, 다운로드에 더해 **analyze(프로필)와 evaluate(Rubric)를 기본으로
함께 돌리고** `reference_video/list.md` 카탈로그 항목까지 추가한다. 즉 "레퍼런스 분석"은 두
가지를 기본으로 한다(끄려면 `--no-evaluate`). 반면 영상 생성 과정의 내부 분석은 `analyze`만
쓰면 된다. 단독 명령 `analyze`와 `evaluate`는 각각 한 가지만 하도록 명확히 분리돼 있고,
`add-reference`가 그 둘을 조합한다.

### verify - 기술 완성도 검증 (하드 pass/fail)

```bash
reel-gen verify ./outputs/run/final.mp4 --input gen.json --storyboard board.json --manifest run.json
```

영상이 테크니컬하게 온전히 완성됐는지 본다. 역할:

- **생성 그래프의 "영상 결과물 확인" 하드 게이트**. 교정 가능한 fail이면 교정 파라미터를
  실어 문제 노드로 되돌려 재생성하고(최대 3회), 통과하거나 소진하면 다음(describe)으로
  진행하며 미해결 fail을 report에 남긴다. 이번 범위의 교정은 loudness 하나다(생성물에 조금
  더 타이트한 loudness 밴드를 걸어 게이트를 살린다). visuals 등 다른 축 교정은 같은 틀에
  향후 추가한다. 설계는
  [../docs/superpowers/specs/2026-07-01-verify-repair-loop-design.md](../docs/superpowers/specs/2026-07-01-verify-repair-loop-design.md).
- 별도 CLI(`reel-gen verify`)로 떼어 돌리면 하드 pass/fail이다(fail이면 exit≠0, repair 없음).

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

### compare - 레퍼런스 대비 유사도 (하드 pass/fail + 개선 델타)

```bash
reel-gen compare --reference ./ref.mp4 --output ./outputs/run/final.mp4
reel-gen compare --reference profiles/ref.json --output profiles/gen.json --out sim.json
```

생성물이 레퍼런스와 **같은 결**인지 잰다. verify(무결성)·evaluate(콘텐츠 효과성)와 달리, 두
`VideoProfile`을 한 자로 재는 유사도 게이트다.

입력 해소는 `analyze`를 재사용한다: `--reference`와 `--output`은 각각 프로필 JSON이거나
영상이며, 영상이면 `_load_profile`이 먼저 `analyze`로 프로필을 뽑고, `.json`이면 그대로
로드한다. 즉 두 입력이 무엇이든 최종적으로 **두 `VideoProfile`을 비교**하는 것이고, `compare`
자체는 순수·결정론(모델 호출 없음)이다. reference/output은 대칭이라 둘 다 영상이든, 둘 다
JSON이든, 섞여도 된다. 영상 재분석은 무겁고(특히 Gemini 지각 계층) 비결정적이라, 이미 프로필
JSON이 있으면 그걸 넘겨 analyze를 건너뛰는 게 싸고 안정적이다. 역할:

- 컷 리듬·보이스·음악·비주얼·자막·톤·아크를 축별로 0~1 채점하고 가중 합산해 `SimilarityReport`를
  낸다. 임계 미달이면 exit≠0.
- **런 모드 유사도 루프의 판정기**: `run --max-iters>1`이면 생성물을 다시 analyze해 compare하고,
  미달 축의 개선 델타를 plan 피드백(`style_feedback`)으로 밀어 넣어 재계획·재생성한다. 이때
  레퍼런스는 루프 시작 전 **한 번만** analyze해 프로필로 재사용하고, 매 반복은 생성물만 다시
  분석한다(위 비용·결정성 이유).

계약은 [similarity-loop.md](similarity-loop.md).

## execute 명령 (ReelProfile → 영상)

`execute`는 Production 페이즈 진입점이다. plan이 동결한 `ReelProfile`만 받아 영상을 만든다.

```bash
reel-gen execute ReelProfile-glow-serum-20260630-204512.json
```

`run`과 분리한 이유: `run`은 상위 입력(영상 목적·텍스트 브리프·단일 에셋)을 받아 plan부터
끝까지 돌리는 반면, `execute`는 동결된 ReelProfile을 받아 Production만 돈다. 비싼 앞 단계
(기획)를 반복하지 않는다.

이게 의미 있는 이유:

- **재실행과 미세 수정**: plan으로 한 번 만든 ReelProfile을 저장해 두면, 자막 한 줄이나
  타이밍만 손본 뒤 같은 ReelProfile을 `execute`에 다시 넣어 영상만 새로 뽑는다.
- **재현**: 같은 ReelProfile은 유사한 영상을 만든다(시드·provenance로 결정론 부분 재현).
  단 환경·가용 리소스가 다르면 ProductionPlan이 갈려 결과가 달라질 수 있다(폴백은
  RunManifest에 기록).

### 전제 조건과 검증

`execute`가 받는 ReelProfile의 `asset_bible`에는 영상 생성에 들어갈 **이미 생성된 이미지의
로컬 경로**(캐릭터·제품·환경)가 들어 있어야 한다. `execute`는 다음을 따른다.

- 실행 전에 에셋 이미지의 로컬 경로가 실제로 존재하는지 확인한다.
- 이미 생성된 에셋·클립이 있으면 재생성을 건너뛰고 조립만 한다(기존 "storyboard 직행"
  execute의 조립-전용 동작을 흡수). 필요한 재료가 없으면 ProductionPlan에 따라 생성한다.
- 영상 생성을 아예 못 하는 누락(필수 에셋 경로 부재)은 누락을 알려 주고 멈춘다(에러 종료).

## rerun 명령 (같은 정체성, 다른 어프로치)

`rerun`은 기존 `ReelProfile`로 다른 어프로치 1편을 다시 뽑는 1-level 명령이다. 정체성
(제품·모델·에셋)은 그대로 두고, 레퍼런스를 무시하고 style부터 새로 뽑아 서사(훅·스토리·
나레이션·음악)를 다시 전개한 새 `ReelProfile`(새 폴더)을 만든 뒤 그걸로 Production을 돌린다.

```bash
reel-gen rerun ReelProfile-glow-serum-20260630-204512.json
```

- **`execute`와 나눈 이유**: `execute`는 프로필을 있는 그대로 렌더한다. 서사를 다시 뽑는 것은
  별개 작업이라 자체 동사로 둔다(예전 `execute --replan` 플래그를 대체). 프로필을 그대로
  다시 렌더할 때는 `execute`, 다른 결과를 원할 때는 `rerun`.
- **매번 다른 결과**: replan은 이전 style을 복사하지 않고 style부터 재생성하므로("같은 시스템,
  다른 결과"), 같은 제품·모델이라도 다른 훅·스토리로 갈린다. 텍스트 LLM 키가 필요하다(없으면
  거절). key_visual은 재생성하고, 이미지 클라이언트가 없으면 원본 커버를 복사해 폴백한다.
- 재전개 그래프와 계약의 정본은 [replan.md](replan.md), 노드 흐름은 [workflows.md](workflows.md).

## 설치와 실행(요약)

빌드된 바이너리를 배포하지 않는다. 저장소를 클론하고 [uv](https://docs.astral.sh/uv/)로
의존성을 깐다. 업데이트는 `git pull` 후 `uv sync`. 자세한 건 [../README.md](../README.md)
"설치".

## 연결 문서

- 생성 단계 내부 계약과 스키마: [pipeline-design.md](../docs/pipeline-design.md)
- 사용자용 요약과 명령/옵션 표: [../README.md](../README.md)
