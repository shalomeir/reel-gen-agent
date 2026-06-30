# 후크 생성기: 계약

상태: 확정. 이 문서는 생성 파이프라인이 첫 1~3초 후크를 어떻게 만들어야 하는지를
고정한다. 무엇을 왜 만드는지의 배경, 유형별 예시, 귀납 근거는
[../docs/hook-insight.md](../docs/hook-insight.md)에 길게 적었다. 여기 specs 문서는
구현이 반드시 따르는 유형 집합, 입출력 스키마, 선택 로직, 게이트, 완료 기준만
못박는다. 코드와 이 문서가 어긋나면 이 문서가 이긴다.

후크는 드라이버 Rubric의 D1(`hook_strength`)이 채점하는 바로 그 구간을 만든다.
따라서 이 계약의 산출물은 [rubric.md](rubric.md)의 D1 판정을 통과하도록 설계한다.

## 한 줄 요약

생성 입력에서 LLM이 후크 유형 1~3개를 골라, 각 유형마다 텍스트·비주얼·오프닝
서사 비트·본문 연결을 한 묶음으로 비결정적으로 생성한다. 출력은 고정 스키마
`HookSet`이며, 콘셉트/스토리보드 단계가 이를 소비한다.

## 후크 유형 (H1~H12)

유형은 상수가 아니라 데이터로 둔다. 코드는 아래 표를 단일 출처로 읽는다. 표를
바꾸면 선택 로직과 프롬프트가 그대로 따라온다. 예시 문구와 슬롯은
`docs/hook-insight.md`에 있고, 여기서는 코드·키·제품 적합도만 고정한다.

| 코드 | 키 | 유형 | 제품 적합도 |
|---|---|---|---|
| H1 | `before_after` | 비포/애프터·시간경과 증명 | 매우 높음 |
| H2 | `problem_solution` | 문제 제기 -> 해결 약속 | 높음 |
| H3 | `secret_knowhow` | 호기심·비밀·노하우 | 높음 |
| H4 | `experiment_proof` | 실험·증명(데모, A/B) | 높음 |
| H5 | `reversal` | 반전·역설·충격 | 중간 |
| H6 | `number_limit` | 숫자·제한(시간·단계) | 높음 |
| H7 | `pov_immersion` | POV·상황 몰입 | 중간~높음 |
| H8 | `confession_relatable` | 개인 고백·공감 | 중간 |
| H9 | `authority_proof` | 권위·사회적 증거 | 높음 |
| H10 | `product_reveal` | 신제품 소개·리빌 | 매우 높음 |
| H11 | `routine_framing` | 루틴 선언 | 높음 |
| H12 | `choice_challenge` | 양자택일·챌린지(참여 유도) | 낮음(변형 필요) |

"제품 적합도"는 이 영상이 제품 PPL일 때 Rubric의 D4(브랜드 통합)·D5(행동 유도)를
얼마나 쉽게 채우는지를 뜻한다. 낮은 유형은 제품 축을 끼워야 D4/D5가 산다.

## 카테고리 -> 기본 유형 매핑

선택의 출발점이다. 상수가 아니라 설정 테이블로 두고, 새 카테고리는 행을 추가한다.

| 카테고리 | 기본 후보 유형 |
|---|---|
| 효능·마스크(skincare efficacy) | H1, H9, H2 |
| 신제품·캠페인(launch) | H10, H3 |
| 멀티스텝 루틴(routine/GRWM) | H11, H6 |
| 정보·교육(info/tutorial) | H3, H6 |
| 비교·시연(demo) | H4, H1 |
| 라이프스타일·참여(lifestyle/engagement) | H7, H12 |

LLM은 이 기본 후보에서 출발하되, 입력 톤·USP에 따라 표 밖 유형도 고를 수 있다.
다만 H12 같은 낮은 적합도 유형을 고르면 제품 축 치환(예: 비교의 한 축을 "사용 전 vs
후" 또는 "제품 A vs B")을 본문 연결에 반드시 포함한다.

## 입력 계약 (`HookRequest`)

생성 입력(`GenerationInput`)에서 파생한다. 새 필드는 최소화하고 기존 스펙을 재사용한다.

- `product`: `ProductSpec`(name, usp, spec, packaging_desc). 후크의 주어.
- `category`: str. 위 매핑 테이블의 키. 없으면 `style`/`product`에서 추론.
- `tone`: list[str]. `StyleSpec.tone` 재사용.
- `platform`: str. `InputMeta.platform`(tiktok/reels/shorts).
- `language`: str. `InputMeta.language`. 후크 텍스트 언어(코퍼스에 비영어 사례 있음, 파라미터다).
- `duration_sec`: float. `InputMeta.duration_sec`. 후크 윈도 길이 산정에 쓴다.
- `count`: int = 3. 생성할 후크 후보 수.
- `forced_type`: str | None. 특정 유형(H1~H12)을 강제할 때. 없으면 LLM이 카테고리 기본에서 선택.
- `style_profile_ref`: str | None. 레퍼런스 프로필 경로. 톤·자막 밀도·언어의 근거 컨텍스트.

## 출력 계약 (`HookCandidate`, `HookSet`)

스키마 정의 위치는 `src/reel_gen_agent/generate/schema.py`다. 콘셉트/스토리보드
단계가 이 모듈에서 임포트해 소비한다. 분석↔생성은 스키마로만 통신한다는 불변식을 지킨다.

### `HookCandidate`
- `hook_type`: str. H1~H12 코드.
- `headline`: str | None. 상단 텍스트 후크. `no_text_visual=True`면 None 가능.
- `bottom_caption`: str | None. 하단 텍스트.
- `reinforce_overlap`: bool = False. 상단·하단에 같은 문구를 겹쳐 박는지.
- `no_text_visual`: bool = False. 텍스트 없이 비주얼·사운드만으로 여는지.
- `visual_direction`: str. 0초 비주얼 지시문(클로즈업/전후 비교/텍스처 확대 등).
- `opening_beat`: str. `narrative_arc`의 첫 비트(problem / reveal / before 등).
- `bridge`: str. 후크 -> 본문 연결. 후크 뒤 1~2컷 안에 올 제품·결과 핵심 장면 한 줄.
- `window_sec`: tuple[float, float]. 후크 노출 구간. 아래 규칙으로 산정.
- `variant`: str | None. "question" 또는 "command"(A/B 변형 구분).
- `rationale`: str. 왜 먹히는지 한 문장(한국어).

### `HookSet`
- `candidates`: list[`HookCandidate`]. `count`개.
- `request`: `HookRequest`. 입력 에코(재현용).
- `selected`: int | None. 게이트에서 사람이 고른 후보 인덱스(미선택이면 None).

## 생성 규칙 (결정론 부분)

지각·창작은 LLM, 산수·검증은 코드로 나눈다. 아래는 코드가 강제하는 결정론 규칙이다.

1. **윈도 길이**: `duration_sec >= 10`이면 `window_sec = (0.0, 3.0)`, 미만이면
   `(0.0, min(2.0, duration_sec * 0.2))`로 좁힌다. 코드가 계산해 덮어쓴다.
2. **유형 유효성**: `hook_type`이 H1~H12 표에 없으면 거부한다.
3. **낮은 적합도 가드**: `hook_type`의 제품 적합도가 "낮음"이면 `bridge`에 제품 축
   치환 문구가 비어 있지 않아야 한다(빈 문자열 거부).
4. **A/B 변형**: `count >= 2`면 같은 유형으로 질문형·명령형 변형을 최소 한 쌍 포함한다.
5. **텍스트/비주얼 정합**: `no_text_visual=True`면 `headline`과 `bottom_caption`은 None,
   `visual_direction`은 비어 있지 않아야 한다.

## 비결정성

LLM 호출에 temperature를 주어 같은 `HookRequest`에도 다른 후크가 나오게 한다(필수
요건). 유형은 매핑·입력으로 좁히되, 문구·비주얼 지시문은 매번 새로 생성한다.
재현이 필요하면 seed를 `HookSet.request`와 함께 기록한다.

## 파이프라인·게이트 연결

- **소비처**: 콘셉트 단계가 `HookSet`을 받아 `GenerationInput.narrative_arc[0]`를
  `opening_beat`로 세우고, 스토리보드 0번 패널(`StoryboardPanel`, `beat="hook"`,
  `t_start=0`, `subtitle_text=headline`, `prompt=visual_direction`)로 펼친다.
  `bridge`는 1~2번 패널의 핵심 장면 설계에 반영한다.
- **게이트**: 다른 단계와 같은 3-모드로 둔다. ask(후보 확인·편집·선택), pass
  (`--force-step-pass hook`이면 0번 후보 자동 채택), run(전 게이트 통과 모드면 자동 채택).
- **검증 연결**: 채택된 후크를 포함한 생성물은 최종적으로 `evaluate`(Rubric)로
  채점된다. D1이 `min_gate_score` 미만이면 후크를 약점 근거로 재생성한다. D4/D5가
  낮으면 `bridge`의 제품 연결을 강화한다. 후크만 강하고 제품이 빈 결과를 막는 장치다.

## 스키마 경계

- `HookType` 표(코드·키·적합도)와 카테고리 매핑은 데이터로 둔다(하드코딩 금지).
- `HookRequest`, `HookCandidate`, `HookSet`은 `generate/schema.py`에 정의한다.
- 생성기 진입 함수는 `generate/hook.py`의 `generate_hooks(request: HookRequest) -> HookSet`
  하나로 둔다. LLM 호출은 이 모듈 안에 가둔다.

## 완료 기준

- `generate/schema.py`에 `HookType`(또는 표 상수), `HookRequest`, `HookCandidate`,
  `HookSet`이 정의된다.
- `generate/hook.py`의 `generate_hooks`가 위 입출력 계약과 생성 규칙을 구현한다.
- 결정론 규칙(윈도 길이, 유형 유효성, 낮은 적합도 가드, A/B 변형, 텍스트/비주얼 정합)이
  테스트로 덮인다. LLM 호출은 목으로 대체한다.
- 카테고리 -> 기본 유형 매핑 표를 바꾸면 선택 후보가 따라 바뀐다(매핑 하드코딩 금지).
- 후크 게이트가 ask/pass/run 3-모드로 동작하고, 채택 결과가 스토리보드 0번 패널로 펼쳐진다.
