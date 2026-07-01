# verify 하드 게이트 + 교정 repair 루프 (execute 그래프)

상태: 설계 (2026-07-01)

## 왜

지금 execute 그래프의 `verify` 노드는 conformance 결과를 state에 기록만 하고 무조건
`describe`로 넘어간다(`add_edge`만, 조건 분기 없음). fail이 나도 파이프라인이 그대로 통과해,
"결함이 있으면 다시 만든다"는 시스템 증거가 없다. 단독 CLI `verify`는 하드 pass/fail인데
그래프 안에서는 소프트라, 이 간극을 메운다.

핵심 제약: **재실행이 결과를 바꿔야 repair가 의미 있다.** `assemble`은 ffmpeg 결정론
연산이라 같은 입력으로 다시 돌리면 같은 fail이 반복된다. 그래서 단순 재실행이 아니라,
실패에서 뽑은 **교정 파라미터**를 다음 재생성에 주입한다. 이번 범위는 그중 결정론이라
재현 가능하고 검증이 깔끔한 **loudness 교정 하나**로 시작한다. visuals(비결정 재생성)는
그래프 골격이 이미 완성돼 있어 나중에 같은 틀로 쉽게 얹는다.

## 무엇을 (이번 스펙)

1. **verify 조건 분기.** `assemble -> verify` 다음을 무조건 엣지에서 조건 엣지로 바꾼다.
   `verify` 노드가 conformance를 돌리고 repair 결정을 내려, `assemble`로 되돌리거나
   `describe`로 진행한다.

2. **loudness 교정 repair.** loudness fail이면 loudnorm 목표를 위반한 경계 안쪽으로
   밀어 넣어 `assemble`을 다시 돌린다. 전체 3회 상한. 소진하거나 교정 불가면 소프트 통과로
   `describe`로 가되 `report.md`에 미해결 fail과 시도 횟수를 남긴다.

3. **생성물 loudness 밴드 주입.** 기본 conformance loudness 범위(-30 ~ -5 LUFS)는
   레퍼런스 기준선이라 너무 넓어(assemble이 -16/-20으로 맞추면 항상 통과) repair가 죽은
   코드가 된다. execute 그래프의 `verify`는 생성물용으로 살짝 타이트한 밴드
   (`lufs_min=-21.0`, `lufs_max=-9.0`)를 주입해 게이트를 살린다. 나머지 임계는 기본값
   그대로. 단독 CLI `verify`와 레퍼런스 검증은 기존 넓은 기본값을 유지한다(이 변경은
   그래프 안에서만).

## 실패 -> 대상·교정 매핑

`generate/repair.py` 새 모듈, 순수 함수:

```python
class RepairAction(BaseModel):
    target: str            # 재생성할 노드 ("assemble")
    loudness_target: float # assemble에 주입할 loudnorm 목표(LUFS)

def plan_repair(report: ConformanceReport, config: ConformanceConfig,
                measured_lufs: float | None, attempts: int,
                max_attempts: int = 3) -> RepairAction | None:
    """conformance fail에서 교정 액션을 뽑는다. 교정 불가/상한 소진이면 None."""
```

규칙(우선순위):

- `report.passed`거나 `attempts >= max_attempts` -> `None` (진행)
- `perceptual.volume_loudness`가 fail이고 `measured_lufs`가 있으면 -> `assemble`,
  교정 목표는 위반 경계 안쪽으로 여유폭(`margin = 1.5`)만큼:
  - 측정치 < `lufs_min` (너무 조용) -> `loudness_target = lufs_min + margin`
  - 측정치 > `lufs_max` (너무 큼) -> `loudness_target = lufs_max - margin`
  - 경계 안쪽으로 미는 방식이라, 음악 베드의 "조용한" 의도를 중앙값으로 뭉개지 않는다.
- 그 밖의 fail(자막 위치, fps/해상도, merge, nodegraph 등 교정 파라미터 없음) -> `None`
  (되돌려도 no-op이므로 미해결로 기록하고 진행)

클리핑(`perceptual.volume_no_clipping`)은 loudnorm이 이미 TP를 진폭 제한하므로 실무상
거의 안 나고, loudness 교정 재믹스로 함께 해소된다. 별도 교정 파라미터를 두지 않는다.

## assemble 파라미터화

`assemble(materials, meta, out_path)`와 내부 `_mux_audio`에 선택 인자
`loudness_target: float | None`을 추가한다. 주어지면 최종 `loudnorm` 목표(`target_i`)를
그 값으로 덮고, 없으면 기존 규칙(-16 voiceover / -20 music bed)을 쓴다. 다른 오디오
믹싱 로직은 그대로.

## 그래프·상태 배선

`ExecState`에 추가:

- `repair_attempts: int` — 지금까지 loudness repair 되돌린 횟수(기본 0)
- `loudness_target: float | None` — assemble에 주입할 교정 목표(없으면 기본 규칙)
- `repair_route: str` — 조건 엣지가 읽을 다음 노드 이름("assemble" | "describe")

노드 변경:

- `_assemble_node`: `Materials`를 만들 때 `state.get("loudness_target")`를
  `assemble(..., loudness_target=...)`로 넘긴다.
- `_verify_node`: 생성물 loudness 밴드를 주입한 `ConformanceConfig`로 conformance를
  돌린다. `measured_lufs`는 `analysis/loudness.py`로 최종 mp4를 직접 재서 얻는다(conformance
  체크의 `actual` 문자열을 파싱하지 않는다 — 결정론 수치 계층을 직접 쓴다). `plan_repair`로
  액션을 구한다.
  - 액션이 있으면: `{"conf_dump", "loudness_target": action.loudness_target,
    "repair_attempts": attempts+1, "repair_route": "assemble"}`
  - 없으면: `{"conf_dump", "repair_route": "describe"}`
- 조건 엣지: `add_conditional_edges("verify", lambda s: s["repair_route"],
  {"assemble": "assemble", "describe": "describe"})`. 기존 `("verify","describe")`
  무조건 엣지는 제거.

되돌아간 `assemble`은 교정 목표로 재믹스 -> `verify` 재검. loudnorm이 목표를 밴드 안으로
당기므로 보통 1회 재생성으로 통과한다. 통과하거나 3회 소진이면 `describe`로 빠진다.

무한 루프 방지: `repair_attempts` 상한이 유일한 출구 보장이다. 조건 엣지는 두 목적지뿐이라
다른 경로로 새지 않는다.

## report 반영

`_report_node`가 만드는 `report.md`(및 RunManifest)에 다음을 남긴다:

- `repair_attempts`: 되돌린 횟수
- 최종 conformance의 미해결 fail 목록(있으면). 3회로도 못 고쳤거나 교정 불가 fail이
  남은 채 진행된 경우를 증거로 보존한다.

## 테스트 (`tests/test_repair.py`, `tests/test_execute_repair.py`)

conformance와 ffmpeg 호출은 모킹. 결정론 층만 실제로 검증한다.

1. **plan_repair 순수 단위 테스트**
   - loudness fail(측정치 -24 < lufs_min -21) -> target ≈ -19.5(= -21 + 1.5) 액션
   - loudness fail(측정치 -3 > lufs_max -9) -> target ≈ -10.5(= -9 - 1.5) 액션
   - passed 리포트 -> None
   - attempts == 3 -> None (상한)
   - 교정 불가 fail(예: template.fps_match만 fail) -> None
2. **그래프 루프 통합 테스트**(conformance를 모킹)
   - 1회차 loudness fail -> 2회차 pass: `verify -> assemble -> verify -> describe` 도달,
     최종 `repair_attempts == 1`, assemble이 교정 target으로 재호출됨
   - 3회 연속 fail: `describe` 도달, `repair_attempts == 3`, report에 미해결 기록
   - 교정 불가 fail: 즉시 `describe`, `repair_attempts == 0`

## 범위 밖 (향후)

- **visuals 교정 repair**: 손상·블랙/플리커 프레임 fail 시 캐시 무시하고 해당 컷 재생성
  (비결정적이라 자가치유 가능). 같은 조건 엣지 틀에 `target="visuals"`와 `regen_shots`를
  더하면 된다. Veo 재호출 비용·캐시 바이패스 구현이 남아 이번 범위에서 뺀다.
- 자막 위치·전환 등 결정론 fail의 파라미터 교정.
- 단독 CLI `verify`에는 repair가 없다(그래프 전용). CLI는 계속 하드 pass/fail 보고만.

## 관련 문서

- [../../../specs/conformance-gate.md](../../../specs/conformance-gate.md) — verify 계약·체크 카탈로그
- [../../../specs/product-design.md](../../../specs/product-design.md) — verify 노드의 소프트/하드 서술(이 스펙으로 갱신 대상)
- [../../../retro.md](../../../retro.md) — "하드 게이트+repair 루프는 향후"로 미뤄둔 항목(이 스펙이 해소)
