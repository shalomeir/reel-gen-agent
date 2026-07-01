# 개발 과정과 기술 분석

README가 "무엇을, 어떻게 쓰는지"라면, 이 문서는 "안에서 어떻게 만들어지는지"다. 파이프라인이
LangGraph 위에 어떻게 올라가 있고, plan과 production 두 페이즈가 각각 어떻게 구현돼 있으며,
모델은 어떤 기준으로 골랐는지를 정리한다. 확정된 계약은 `specs/`가 정본이고, 이 문서는 그
결정들을 한눈에 잇는 지도다. 숫자나 인터페이스가 어긋나면 `specs/`를 믿는다.

## 1. 큰 그림: 분석과 생성을 스키마로 가른다

이 시스템의 뼈대는 "스타일을 코드에 박지 않는다"는 원칙 하나다. 스타일은 레퍼런스에서
측정하고, 재사용 가능한 데이터(`VideoProfile`)로 표현하고, 그 데이터로 생성을 끌고 간다.
그래서 분석과 생성은 직접 서로를 부르지 않고 pydantic 스키마로만 통신한다
(`analysis/profile.py`, `generate/schema.py`). 가장 자주 바뀌는 이미지·영상 백엔드를 갈아
끼워도 스키마 경계 한 곳만 손대면 되도록 한 설계다. 배경은
[docs/architecture.md](docs/architecture.md)와 [specs/ADR.md](specs/ADR.md) ADR-0003에 있다.

레퍼런스를 프로파일링하는 그 분석기가 생성물도 프로파일링한다. 그래서 레퍼런스와 출력이 같은
자로 판단된다. 유사도 비교(`compare`)와 콘텐츠 채점(`evaluate`)이 모두 이 한 엔진 위에서 돈다.

## 2. LangGraph로 짠 두 페이즈

생성 파이프라인은 LangGraph `StateGraph` 두 개다. 노드는 공유 상태를 읽고 부분 업데이트만
돌려주며, 각 노드 span은 로컬 trace(옵션으로 Langfuse)에 남는다. 그래프 구조의 정본은
[specs/workflows.md](specs/workflows.md)이고, 여기서는 구현 관점의 요점만 짚는다.

- **Planning** (`generate/plan_graph.py`, `StateGraph(PlanState)`): 입력 셋을 받아 컨셉, 스타일,
  에셋, 스토리보드를 거쳐 `ReelProfile`(profile.json)로 동결한다.
- **Production** (`generate/execute_graph.py`, `StateGraph(ExecState)`): 그 profile을 받아 영상
  모델 능력에 맞춰 재료를 만들고 조립·검증한다.

두 페이즈는 오직 `ReelProfile` 스키마로만 통신한다. 그래서 `plan`과 `execute`를 따로 개발하고
따로 실행할 수 있다. `run`은 둘을 한 번에 잇고, `chat`은 앞단에 대화형 입력 수집을 더한다.

### 왜 함수 호출이 아니라 그래프인가

파이프라인은 선형이 아니다. 훅과 스토리보드가 서로 맞을 때까지 오가는 핑퐁 루프가 있고,
검증에서 떨어지면 되돌아가 다시 조립하는 repair 루프가 있고, 오디오 세 갈래는 병렬로
갈라졌다 다시 모인다. 조건부 엣지와 fan-out/fan-in을 명시적으로 그릴 수 있는 그래프가 이
흐름을 코드보다 정확히 담는다. 노드마다 trace span이 남아 어디서 무엇이 결정됐는지 되짚기도
쉽다.

## 3. plan은 어떻게 구현돼 있나

Planning 그래프는 정체성을 먼저 잠그고, 스타일이 콘텐츠를 앞에서 이끌고 뒤에서 맞추는 두
접점을 갖는 구조다. 노드 순서(`plan_graph.py`가 정본):

```
intake -> reference_seed -> product -> character -> environment
      -> style(초안) -> hook <-> storyboard -> style_refine
      -> narration -> music -> write_profile
```

핵심만 짚으면 이렇다.

- **intake**: 입력을 판별한다. `objective`(영상 목적)는 필수라 없으면 진입을 막는다. 기본
  로케일은 영어·미국이고, 입력이 명시할 때만 언어와 지역을 바꾼다.
- **reference_seed**: 레퍼런스가 있으면 분석해 `ReelProfile` 베이스라인 전체를 시딩한다. 컷
  리듬만이 아니라 톤, 페이싱, 자막 스타일, 후크, 음악 다이내믹, 내러티브 아크까지 씨앗으로
  삼는다.
- **product / character**: 제품과 캐릭터를 텍스트로 규정한 뒤 그 자리에서 히어로·패키지샷과
  캐릭터 시트샷을 Nano Banana로 생성한다. 이 이미지들이 뒤의 스틸·영상 일관성의 근거다.
  제품은 URL·이미지·사용자 서술로만 잡고 추정으로 지어내지 않는다(정본
  [specs/product-source.md](specs/product-source.md)).
- **hook <-> storyboard 핑퐁**: 훅은 첫 1~3초 전용 노드로 비결정적(temperature)으로 생성한다.
  스토리보드가 그 훅으로 스토리가 잘 안 열리면 피드백을 내고, 조건부 엣지가 최대 2회 훅을
  다시 부른다. 훅과 스토리를 함께 맞춰 나가는 루프다. 훅 계약은
  [specs/hook-generator.md](specs/hook-generator.md), 유형·배경은
  [docs/hook-insight.md](docs/hook-insight.md).
- **write_profile**: 모든 산출을 `AssetBible`로 조립하고 `ReelProfile`로 동결해 `plan/`에 쓴다.
  이미지 경로는 상대명이라 profile이 이식 가능하다.

`rerun`은 정체성 노드(product/character/environment)를 건너뛰고 style부터 서사·음악까지만 다시
도는 `replan` 서브그래프(`generate/replan_graph.py`)를 쓴다. 계약은
[specs/replan.md](specs/replan.md).

## 4. production은 어떻게 구현돼 있나

Production 그래프는 능력에 맞춰 의도를 해소하고, 영상을 순차로 뽑은 뒤 오디오를 병렬로
붙이고, 하드 게이트로 검증한다. 노드 순서(`execute_graph.py`가 정본):

```
load -> production_plan -> stills -> visuals
     -> (voice ‖ bgm ‖ sfx) -> assemble -> verify -> describe -> evaluate -> report
```

- **production_planner**: `ReelProfile`의 생산 의도를 영상 모델의 capability matrix(멀티샷,
  voice 동시 생성, 클립 길이, 해상도)와 가용 리소스에 맞춰 `ProductionPlan`으로 해소한다.
  voice 전략, 멀티샷 여부, 샷 렌더러(i2v / 켄 번스 폴백 / canvas), bgm·sfx를 여기서 정하고,
  적용한 폴백을 `RunManifest`에 남긴다. 이식 가능한 의도(ReelProfile)와 머신 의존 실행
  계획(RunManifest)을 나눈 게 핵심이다.
- **visuals(순차)**: 패널별 image-to-video를 순차로 돌린다. 컷마다 이전 컷을 연결해 일관성을
  유지하고, 씬 네이티브 오디오도 여기서 영상과 함께 난다. 영상 모델이 꺼지거나 한 컷이
  실패하면 그 컷만 스틸+켄 번스 모션으로 폴백해 몽타주를 유지한다.
- **오디오 3노드(병렬 fan-out)**: `voice`(나레이션 TTS, voiceover일 때만), `bgm`(Lyria),
  `sfx`(편집 효과음, 옵션)가 정적 엣지로 병렬 실행되고 `assemble`이 fan-in으로 모은다. voice는
  캐릭터 설정에서 유도한 `VoiceSpec`으로 만들어 톤 일관을 지킨다.
- **assemble**: 결정론 조립이다. 클립 concat, 트랜지션, 오디오 mux, 투명 자막 PNG 오버레이
  (컬러 이모지 보존), 워터마크까지 한다.
- **verify(하드 게이트 + repair 루프)**: conformance fail이 있으면 `plan_repair`가 교정
  액션을 만들고 `verify->assemble` 백엣지로 되돌아가 재조립한다(주로 loudness 재믹싱, 최대
  3회). clean이거나 소진하면 describe로 넘어간다. 계약은
  [specs/conformance-gate.md](specs/conformance-gate.md).
- **describe / evaluate / report**: 업로드 자산(`upload.md`)을 만들고, 드라이버 Rubric으로
  소프트 채점하고, 회차 리포트(`report.md`)를 남긴다.

## 5. 검증 3종을 한 엔진 위에 얹은 이유

같은 분석 엔진 위에 성격이 다른 세 검사를 얹었다. 축을 나눠 서로 다른 질문에 답하게 한
설계다.

- **compare(유사도)**: 생성물이 레퍼런스와 같은 결인가. 두 `VideoProfile`을 축별로 비교해
  미달이면 delta를 plan 피드백으로 밀어 넣는다(정본 [specs/similarity-loop.md](specs/similarity-loop.md)).
- **verify(적합성)**: 의도대로 온전히 만들어졌는가. 하드 pass/fail 게이트다.
- **evaluate(효과성)**: 콘텐츠로서 먹히는가. 소프트 점수라 권고로만 쓴다(정본
  [specs/rubric.md](specs/rubric.md), 배경 [docs/rubric.md](docs/rubric.md)).

## 6. 모델 선택 기록

용도마다 어떤 모델을 왜 골랐는지, 무엇을 폴백·홀딩으로 뒀는지는
[specs/ai-model-records.md](specs/ai-model-records.md)가 정본이다. 원칙은 단일 필수 키
약속(`GEMINI_API_KEY` 하나로 분석·이미지)을 지키면서, GCP 자격이 있으면 멀티모달 호출을
Vertex lane으로 올려 크레딧을 쓰는 것이다. 텍스트 레인만 예외로, 카피 품질이 결과를 좌우해
Gemini 3.1 Pro와 Claude Opus를 일급으로 비교한다. 도구·라이브러리를 왜 골랐는지는
[docs/ToolnModels.md](docs/ToolnModels.md)에 따로 있다.

## 7. 더 읽을 것

- 파이프라인 단계별 세부 계약: [docs/pipeline-design.md](docs/pipeline-design.md)
- 분석 계층 내부 동작: [docs/analysis.md](docs/analysis.md)
- 데이터 스키마와 출력 폴더 구조: [specs/information-schema.md](specs/information-schema.md)
- 설계 결정 로그: [specs/ADR.md](specs/ADR.md)
- 회고(가정·한계·개선 방향): [retro.md](retro.md)
