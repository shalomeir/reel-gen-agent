# report 노드 예상 비용 추정 설계 (2026-07-01)

상태: 확정. report 노드가 회차 리포트에 "예상 비용"을 모델별 내역과 함께 남긴다.

## 배경과 의도

`report.md`는 이미 사용 모델을 한 줄로 적지만, 이 회차를 만드는 데 든 돈이 얼마인지는
보여주지 않는다. 채점자와 운영자가 "같은 시스템, 다른 입력"의 비용 감각을 잡을 수 있게,
회차마다 모델별 단가와 실사용량을 곱한 **예상 비용**을 리포트에 넣는다.

핵심 제약: **record(report) 쪽만 수정한다.** 생성 파이프라인(materials, stills,
production_graph 흐름)은 건드리지 않는다. 비용은 report 시점에 이미 관측 가능한 데이터
(`ReelProfile`, `ProductionPlan`, `RunManifest`, conformance/rubric 결과)에서 계산한다.

정확도보다 정직함을 우선한다. 실제 청구가 아니라 공개 단가 근사치 기반 **예상치**이며,
로컬 폴백(ken_burns, 합성 BGM)은 $0으로 잡고, 반영하지 못하는 부분은 caveat로 명시한다.

## 인터페이스

### 새 스키마 (`generate/schema.py`)

```python
class CostLine(BaseModel):
    label: str            # 항목(패널 스틸 / 영상 클립 / BGM / 나레이션 / 효과음 / 품질 평가)
    model: str            # 실제/유효 모델 ID 또는 로컬 백엔드명
    unit: str             # 초 / 장 / 1k자 / 호출 / 클립
    quantity: float
    unit_price_usd: float
    subtotal_usd: float
    note: str | None = None

class CostReport(BaseModel):
    as_of: str            # 단가 기준일(PRICING_AS_OF)
    currency: str = "USD"
    lines: list[CostLine] = Field(default_factory=list)
    total_usd: float = 0.0
    caveats: list[str] = Field(default_factory=list)
```

`FinalReport`에 `cost: CostReport | None = None`을 추가한다. 기존 `models_used`는 유지한다.

### 단가 테이블 (`generate/cost.py`, 신규)

`PRICING_AS_OF = "2026-07-01"`와 `PRICING` 딕셔너리를 한 곳에 둔다. 값은 **공개 근사치**이며
이 파일만 고치면 갱신된다.

| 모델 ID | 단위 | 근사 단가(USD) |
|---|---|---|
| veo-3.1-fast-generate-001 | 초 | 0.15 |
| veo-3.1-generate-001 | 초 | 0.40 |
| veo-3.1-lite-generate-001 | 초 | 0.10 |
| fal-ai/kling-video/o3/pro/reference-to-video | 초 | 0.28 |
| fal-ai/kling-video/o3/standard/reference-to-video | 초 | 0.14 |
| fal-ai/kling-video/o3/pro/image-to-video | 초 | 0.28 |
| fal-ai/kling-video/o3/standard/image-to-video | 초 | 0.14 |
| gemini-3.1-pro-image-preview | 장 | 0.12 |
| gemini-3.1-flash-image-preview | 장 | 0.039 |
| lyria-002 | 초 | 0.06 |
| eleven_v3 | 1k자 | 0.18 |
| gemini-3.1-flash-tts-preview | 1k자 | 0.01 |
| elevenlabs-sfx | 클립 | 0.08 |
| gemini-2.5-flash (VLM) | 호출 | 0.02 |

로컬 백엔드 `ken_burns` / `synth` / `none`은 $0.

단가 조회는 정확 매칭 우선, 없으면 부분 매칭(예: `kling`+`pro`+`reference`)으로 폴백한다.
어느 쪽도 못 찾으면 $0으로 잡고 caveat에 "미등록 모델: <id>"를 남긴다.

### `estimate_cost(profile, plan, manifest, conformance, rubric, env) -> CostReport`

report 시점 관측값에서 실사용량을 유도한다. 유효 모델은 `plan`이 이미 해소한 값을 쓰되,
빠른 반복용 환경 오버라이드(`REEL_VIDEO=ken_burns`, `REEL_BGM=synth`)와 키 유무를 함께 본다.

- **패널 스틸(이미지)**: `quantity = still_image가 있는 패널 수`. 모델 = 히어로 이미지
  (`GEMINI_IMAGE_MODEL_HERO`, 기본 `gemini-3.1-pro-image-preview`). 스틸은 `hero=True`로
  생성되므로 히어로 단가를 쓴다. note: 사용자 제공 스틸이 섞일 수 있어 추정.
- **영상 클립**: `clips = len(manifest.panel_segments)`, `seconds = Σ max(0.5, t_end-t_start)`
  (still_image 있는 패널만; materials 로직과 정렬). 유효 모델:
  - `plan.video_model`이 없거나 `ken_burns`거나 `REEL_VIDEO=ken_burns`면 ken_burns($0).
  - 아니면 `plan.video_model`을 PRICING에서 조회(초당 단가 x seconds).
- **BGM**: `plan.bgm == "gen"`이고 `REEL_BGM != synth`이고 `GOOGLE_CLOUD_PROJECT`가 있으면
  Lyria(`LYRIA_MODEL`, 기본 `lyria-002`), seconds = 영상 총초. 아니면 합성 베드($0).
- **나레이션(TTS)**: `plan.voice_strategy == "separate_tts"`이고 나레이션 대사가 있으면
  `chars = Σ len(line.text)`. `ELEVENLABS_API_KEY`가 있으면 `eleven_v3`, 없으면
  `gemini-3.1-flash-tts-preview`. 단위 1k자.
- **효과음(SFX)**: 현재 파이프라인 미배선이라 기본 quantity 0(라인 생략). PRICING에
  `elevenlabs-sfx`를 미리 둬서, 배선되어 집계가 붙으면 자동 반영된다.
- **품질 평가(VLM)**: `rubric`이 비어 있지 않으면 `use_vlm`이 켜졌던 것이므로
  conformance VLM + rubric = 2회. 비어 있으면 0회. 모델 = `GEMINI_ANALYSIS_MODEL`
  (기본 `gemini-2.5-flash`).

quantity가 0인 항목은 라인에서 생략한다. `total_usd`는 subtotal 합.

caveats(항상):
- 단가는 공개 근사치, 실제 청구와 다를 수 있음(기준일 표기).
- ken_burns/합성 BGM 등 로컬 폴백은 $0.
- 기획·카피 텍스트 LLM(컨셉/훅/스토리보드/대사)은 별도 planning 단계라 미포함.
- SFX(ElevenLabs)·Kling O3는 배선되면 자동 반영, 현재 미배선분은 미집계.
- 이미지 수는 스틸 있는 패널 기준 추정.
- `plan.fallbacks_applied`가 있으면 그대로 나열.

### `report.py` 배선

- `build_final_report`가 `estimate_cost(...)`로 `report.cost`를 채운다. 시그니처는 그대로.
- `render_report_md`가 `## 사용 모델` 다음에 `## 예상 비용` 섹션을 렌더한다: 마크다운 표
  (항목/모델/단위/사용량/단가/소계) + 합계 행 + 기준일 헤더 + caveats 불릿.

## 출력 예시

```
## 예상 비용 (단가 기준일 2026-07-01, USD, 실제 청구와 다를 수 있음)

| 항목 | 모델 | 단위 | 사용량 | 단가 | 소계 |
|---|---|---|---|---|---|
| 패널 스틸 | gemini-3.1-pro-image-preview | 장 | 5 | $0.120 | $0.600 |
| 영상 클립 | veo-3.1-fast-generate-001 | 초 | 12.0 | $0.150 | $1.800 |
| BGM | lyria-002 | 초 | 12.0 | $0.060 | $0.720 |
| 나레이션 | eleven_v3 | 1k자 | 0.30 | $0.180 | $0.054 |
| 품질 평가 | gemini-2.5-flash | 호출 | 2 | $0.020 | $0.040 |
| **합계** |  |  |  |  | **$3.214** |

- 단가는 공개 근사치이며 실제 청구와 다를 수 있음
- ken_burns/합성 BGM 등 로컬 폴백은 $0으로 계산
- 기획·카피 텍스트 LLM은 별도 planning 단계라 미포함
```

## 완료 기준

- `report.md`에 모델별 비용 표와 합계, 기준일, caveats가 렌더된다.
- 로컬 폴백(ken_burns/synth) 회차는 해당 라인이 $0 또는 생략된다.
- materials/stills/production_graph 흐름 코드는 변경되지 않는다.
- `pytest -q`, `mypy`, `ruff` 통과. report/cost 단위 테스트가 표와 합계를 검증한다.
