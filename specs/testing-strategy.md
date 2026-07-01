# 테스트 전략

상태: 확정. 이 문서는 무엇을 어떻게 검증하는지를 정한다. 기술 스택은
[trd.md](trd.md)에, 두 검증 게이트의 계약은 [conformance-gate.md](conformance-gate.md)와
[rubric.md](rubric.md)에, 실행 로그와 trace는 [logging-strategy.md](logging-strategy.md)에
있다. 이 문서가 테스트 정본이다. TRD는 요약과 링크만 둔다.

## 한 줄 요약

검증은 세 계층이다. 결정론 단위 테스트가 토대를 깔고, 두 검증 게이트(conformance,
rubric)가 결과물을 판정하며, 레퍼런스 골든이 회귀 기준선을 잡는다. 외부 모델 호출은
전부 목으로 막고, 결정론 층은 실제 단언으로 덮는다.

## 세 계층

### 1. 결정론 단위 테스트 (토대)

재현 가능한 수치를 내는 코드를 실제 단언으로 덮는다.

- **분석 로컬 층**: scenedetect 컷 분포, librosa 오디오 다이내믹, opencv 팔레트와 밝기,
  프레임 샘플러의 black/freeze/flicker 지표, BS.1770 LUFS와 피크. 합성하거나 고정한
  입력으로 기대 수치를 단언한다.
- **스키마 밸리데이터**: `generate/schema.py`의 `InputMeta` 가드레일(종횡비 9:16,
  해상도 상한 1080x1920, 길이 1~60초, 프레임레이트 {24, 25, 30, 50, 60})이 허용값을 통과시키고
  위반값을 거부하는지 단언한다.
- **Rubric 수식**: D1~D7 점수 합산, D1/D2 곱셈 게이트, D3~D7 가산 로직을 고정 입력으로
  단언한다.
- **Conformance 결정론 체크**: 미디어 무결성, 템플릿 적합성, 볼륨(LUFS/클리핑), 머지
  무결성, 스키마 검증을 단언한다.

### 2. 게이트 테스트 (판정)

영상 단계 뒤 두 게이트가 의도대로 통과시키고 거르는지 본다.

- **합성 결함 클립으로 fail 단언**: 깨진 컨테이너, 검은 화면, 무음 클립을 코드로 만들어
  conformance가 해당 결함 카테고리로 `fail`을 내는지 단언한다.
- **머지 위반 단언**: 합성한 `RunManifest`와 `Storyboard`로 노드 산출물이 빠진 상황을
  만들어, conformance가 머지 무결성 위반을 잡는지 단언한다.
- **VLM/지각 체크는 목**: 자막 위치, 효과, 전환 같은 멀티모달 판단은 외부 호출이라
  목으로 막는다. 키가 없으면 `skip`이고, skip은 통과로 친다. 게이트가 키 부재로 막히지
  않는다.

### 3. 레퍼런스 골든 (회귀 기준선)

잘 만든 레퍼런스 영상은 두 게이트를 통과해야 한다. 이를 회귀 기준선으로 쓴다.

- 레퍼런스는 템플릿과 매니페스트가 없어 conformance의 intrinsic 체크만 돌고(나머지
  skip), 모두 PASS여야 한다.
- rubric은 레퍼런스에서 기준선 점수가 나오는지 확인한다.
- 결과는 `evals/`(conformance는 `evals/conformance/`)에 남긴다. `evals/`는 gitignore라
  재생성 가능한 산출물로 둔다.

## 두 게이트의 이중 용도

두 게이트는 그래프 안의 노드인 동시에 단독 CLI로도 떼어 돌린다. 그래프가 미구현이어도
단독 명령은 지금 동작한다.

- `reel-gen verify <video> [--input ... --storyboard ... --manifest ...]` — conformance.
- `reel-gen evaluate <video>` — rubric.

단독 CLI에서 conformance가 fail이면 exit≠0이다. 그래프 안에서는 현재 conformance를 소프트로
기록만 하고 다음으로 진행한다(fail 시 결함 노드만 재생성하는 하드 게이트+repair 루프는 향후,
[../docs/Retrospective.md](../docs/Retrospective.md)). 흐름의 정본은
[conformance-gate.md](conformance-gate.md)와 [product-design.md](product-design.md)에 있다.

## 로깅과 trace 계층 테스트

관측 계층도 결정론 층으로 덮는다. 자세한 설계는 [logging-strategy.md](logging-strategy.md).

- **이벤트 emit 단언**: 노드 시작/종료, 게이트 결정, 모델 호출이 `TraceEvent`로 emit되고
  스키마를 만족하는지 단언한다.
- **로컬 sink는 항상 동작**: `LocalJsonlSink`가 키 없이도 `logs/<session_id>/<run_id>/trace.jsonl`을
  쓰는지 단언한다(진실의 원천).
- **Langfuse sink는 옵션**: `LANGFUSE_*`가 없으면 `LangfuseSink`가 무력화되고, 그래도
  로컬 trace는 온전한지 단언한다.
- **레다크션**: 키와 자격증명, 토큰이 기록 전 마스킹되는지 단언한다.

## 규율과 실행

- 단위 테스트는 독립이고 데이터를 스스로 만든다. 외부 모델 호출(Gemini, 영상 백엔드 등)은
  목으로 막는다.
- 영상이 필요한 테스트는 `reference_video/` 아래 mp4를 쓰고, 없으면 skip한다.
- 결정론 층은 80% 이상 커버리지를 목표로 한다.
- 일련의 변경 뒤에는 `.venv`에서 `ruff check src tests`, `ruff format src tests`, `mypy`,
  `pytest -q`를 돌린다. 반복 중에는 전체 스위트보다 해당 테스트 하나를 먼저 돌린다.
