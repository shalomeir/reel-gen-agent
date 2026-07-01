# 켄 번스 폴백 모션 개선 설계 (2026-07-01)

## 배경

켄 번스 폴백(`backends/ken_burns.py`)은 영상 백엔드 키가 없을 때 스틸을 줌/팬해
클립으로 만드는 워킹 스켈레톤 기본 경로다. 두 가지 문제가 있다.

1. **지터(드드득)**: 현재 `scale=W:H -> crop=W:H -> zoompan(s=WxH)` 순서라 zoompan
   입력과 출력 해상도가 같다. zoompan이 매 프레임 crop 좌표/배율을 정수 픽셀로
   반올림하며 튄다. 느린 줌일수록 프레임당 이동이 1px 미만이라 더 심하다.
2. **단조로움**: 전 컷이 동일한 중앙 선형 줌인이라 다양성이 없다.

폴백 경로이므로 과한 작업은 피한다. 어색해지기 쉬운 효과는 아예 넣지 않는다.

## 결정

### A. 지터 해결 - 필터 추가 없이 다운스케일 순서만 제거

오버샘플 필터를 추가하지 않는다. 대신 스틸을 먼저 `W:H`로 줄이지 않고, **원본
해상도에서 9:16 비율로 crop만** 한 뒤 zoompan이 최종 `s=WxH`로 축소하게 한다. 패널
스틸은 보통 고해상도(히어로 4K)라 그 해상도가 서브픽셀 이동의 여유가 되어 별도
오버샘플 없이 매끄러워진다. 원본이 작으면 예전과 동일(더 나빠지지 않음).

### B. 모션 4종 (어색한 팬은 채택 안 함)

| 모션 | 배율/이동 | 용도 |
|---|---|---|
| `zoom_in_slow` | 1.0 -> 1.06 중앙 줌인 | 일반 컷(교대) |
| `zoom_out_slow` | 1.06 -> 1.0 중앙 줌아웃 | 일반 컷(교대) |
| `push_in` | 1.0 -> 1.12 중앙 줌인 | hook 컷 |
| `product_push_in` | 1.0 -> 1.18 중앙 줌인(강) | 제품 강조 컷(product_lock) |
| `static` | zoompan 미사용, 스틸 반복 | 정지가 꼭 필요할 때만(기본 미사용) |

전부 중앙 기준이라 팬처럼 흔들리지 않는다. 좌우 팬은 어색해지기 쉬워 채택하지 않는다.
`static`은 지터가 원천 차단되지만 `not_frozen`을 건드려 기본 경로에서는 쓰지 않는다.

### C. 매핑 (beat + 제품 잠금 1차 선택, 나머지는 교대)

- `hook -> push_in` (시선을 잡는 또렷한 줌인)
- **제품 강조 컷(`product_lock=True`)** -> 제품으로 줌인. 연속되면 강한 줌인
  (`product_push_in`)과 약한 줌인(`zoom_in_slow`)을 번갈아, 방향은 항상 안쪽(제품)으로
  두되 인접 컷 경계는 다르게 한다. "유저가 제품을 강조할 때 그 제품으로 줌인" 요구를 만족.
- 그 외 일반 컷(problem/discovery/reaction/None) -> `zoom_in_slow`와 `zoom_out_slow`를
  번갈아 쓴다. 일반 컷 순번(홀짝)으로 교대해 인접 클립의 경계 프레임이 달라지고, 스틸이
  비슷해도 컷 감지기가 경계를 잡기 쉽다.

영상 백엔드(Veo/Kling)에도 이 모션이 카메라 지시문으로 전달된다: `materials._veo_prompt`가
모션명을 "slow push-in zooming into the product" 같은 문장으로 바꿔 패널 프롬프트에 붙여,
켄 번스든 실 영상이든 같은 컷 무빙 의도를 공유한다.

## 인터페이스 (아키텍처 경계 유지)

- **선택(데이터)은 plan**: `ProductionPlan.panel_motions: list[str]` 추가.
  `resolve_plan`이 패널 `beat`로 채운다. ken_burns 렌더러일 때만 의미가 있고, i2v면
  무시한다.
- **렌더링(메커니즘)은 backend**: `KenBurnsBackend.render_panel(..., motion="zoom_in_slow")`.
  모션명 -> ffmpeg 식은 backend 내부에 둔다. `static`은 zoompan 없는 단순 경로.
- **매핑 함수** `motion_for_panel(panel, general_index, product_index) -> str`는
  `production_plan.py`에 둔다(패널 beat + `product_lock`로 선택).
- `materials.py` 루프에서 `plan.panel_motions[i]`를 `render_panel`에 넘긴다.

## 게이트

`conformance` `not_frozen`(`freeze_min_diff=2.0`)은 **영상 전체의 평균 인접프레임차**
기준이다. static 컷이 섞여도 나머지 움직이는 컷 덕에 평균이 임계값을 넘어 통과한다.
그래서 게이트는 그대로 둔다. 정지 컷 비중이 큰 릴이 실제로 fail 나면 그때 완화한다.

## 테스트

- `motion_for_panel` 매핑 단위 테스트(hook/제품 컷/일반 컷 교대, 결정적).
- `render_panel`의 각 모션이 ffmpeg 실행에 성공: `zoom_in_slow`/`push_in`은
  `not_frozen` 임계값을 넘기고, `static`은 정지(임계값 미만)임을 확인.
- 기존 `test_ken_burns` duration/resolution 테스트 유지.
