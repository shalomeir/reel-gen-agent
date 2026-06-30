# 로깅 전략

상태: 확정. 이 문서는 실행을 어떻게 기록하고 관측하는지를 정한다. 기술 스택은
[trd.md](trd.md)에, 테스트는 [testing-strategy.md](testing-strategy.md)에, 산출물 폴더
규약은 [pipeline-design.md](../docs/pipeline-design.md)에 있다. 이 문서가 로깅 정본이다.

## 한 줄 요약

로컬 trace가 진실의 원천이고 항상 켜진다. Langfuse는 옵션 sink로, 키가 있을 때만 붙는다.
LangGraph 노드와 게이트, 모델 호출은 하나의 이벤트 스트림을 emit하고, 그 스트림을 여러
sink가 구독한다. 키가 없거나 Langfuse를 꺼도 로컬 trace만으로 실행이 온전히 남는다.

## 원리: 단일 이벤트 스트림, 다중 sink

관측을 특정 백엔드에 묶지 않는다. 그래프는 `TraceEvent`를 emit하기만 하고, 어디에
쓰이는지는 모른다. sink를 갈아끼워도 그래프 코드는 그대로다.

```
LangGraph 노드 / 게이트 / 모델 호출
        │  TraceEvent emit
        ▼
   TraceEmitter ──► LocalJsonlSink   (항상 on, 키 불필요. 진실의 원천)
                ├─► LangfuseSink     (LANGFUSE_* 있을 때만)
                └─► stdlib logging   (session.log / run.log, 사람 판독)
```

- **LocalJsonlSink**: 항상 동작한다. `trace.jsonl`에 구조화 이벤트를 한 줄에 하나씩 쓴다.
  키가 없어도, Langfuse가 죽어도 이 sink는 멈추지 않는다.
- **LangfuseSink**: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`가 있을
  때만 활성화된다. 없으면 조용히 무력화되고 로컬 trace는 그대로 남는다. Langfuse 호출
  실패는 실행을 막지 않는다(관측은 부수 효과지 본 경로가 아니다).
- **stdlib logging**: 사람이 읽는 서술 로그를 남긴다. 레벨은 `LOG_LEVEL`(기본 INFO),
  `--verbose`로 DEBUG.

## 폴더 구조

세션이 단위다. 챗 1회가 1 세션이고 그 안에서 여러 run이 돈다. 런 모드와 단독 명령은
세션 1개에 run 1개다.

```
logs/<session_id>/
  session.log            # 세션 전체 사람 판독 로그 (모든 run/명령을 가로지름)
  <run_id>/
    trace.jsonl          # 그 run의 구조화 이벤트 (노드/게이트/모델호출 span)
    run.log              # 그 run의 사람 판독 상세
```

- **session_id**: 형식 `YYYYMMDD-HHMMSS-<짧은해시>`. 챗 1회 = 1 session(여러 run 가능),
  런/단독 명령 1회 = session 1 + run 1.
- **run_id**: 생성 run은 `outputs/<run_id>/`와 같은 키를 써서 로그와 산출물이 1:1로
  맞물린다. 단독 명령(verify, evaluate, analyze)은 run 개념이 없으므로 명령 스코프 id
  (`verify-<ts>`, `analyze-<ts>` 등)를 써서 같은 폴더 규약에 태운다.
- `logs/`는 재생성 가능한 산출물이라 `.gitignore`에 둔다. 로테이션과 보존 정책은 두지
  않는다. 로컬에서 필요하면 수동으로 정리한다.

## Langfuse 매핑

로컬 단위와 Langfuse 개념을 1:1로 맞춘다. 같은 식별자를 양쪽에 쓰므로 로컬 trace와
Langfuse 대시보드를 식별자로 대조할 수 있다.

| 로컬 | Langfuse |
|---|---|
| session_id | session |
| run_id | trace |
| 노드 한 번 실행 | span |
| 모델 호출 | generation(span) |

## TraceEvent 스키마

구조화 이벤트는 pydantic 모델로 정의하고 `trace.jsonl`에 직렬화한다. 큰 산출물(이미지,
영상, 스토리보드)은 본문에 담지 않고 `outputs/<run_id>/` 경로로 참조만 남긴다.

| 필드 | 설명 |
|---|---|
| `ts` | ISO8601 타임스탬프 |
| `session_id` | 세션 식별자 |
| `run_id` | run 또는 명령 스코프 식별자 |
| `node` | 노드 이름(concept, asset_bible, storyboard, video, verify, evaluate 등) |
| `event` | `node_start`, `node_end`, `gate`, `model_call`, `error` |
| `gate_decision` | 게이트 이벤트일 때 `ask`/`pass`/`edit` |
| `model` | 모델 호출일 때 id, 백엔드, 지연, 가능하면 토큰과 비용 |
| `status` | `ok`/`fail`/`skip` |
| `payload_ref` | 큰 산출물의 outputs 경로 참조 |
| `message` | 짧은 사람 판독 메모(선택) |

## 보안

- **키와 자격증명은 절대 로그에 남기지 않는다.** API 키, 서비스계정, 토큰은 기록 전
  레다크션한다.
- 프롬프트 본문은 디버깅에 필요하므로 남기되, 그 안에 섞인 토큰류는 마스킹한다.
- 개인정보는 로그에 남기지 않는다. 사람 식별이 가능한 입력이 들어오면 레다크션한다.

## 어디서 무엇을 기록하나

- **생성 그래프**: 노드마다 `node_start`/`node_end`, 게이트마다 `gate`(결정 포함), 외부
  모델 호출마다 `model_call`을 emit한다. 재시도(tenacity)는 시도별로 이벤트를 남긴다.
- **두 검증 게이트**: verify와 evaluate는 판정 결과(PASS/FAIL, 점수)를 이벤트로 남기고,
  상세 리포트는 `evals/`에 둔다. trace는 그 경로를 `payload_ref`로 가리킨다.
- **분석**: analyze는 결정론 측정과 Gemini 호출을 이벤트로 남기고, 프로파일은
  `profiles/`에 둔다.
