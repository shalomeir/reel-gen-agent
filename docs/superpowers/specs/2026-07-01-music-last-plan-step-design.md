# music을 plan 마지막 단계로 이동 (스토리·나레이션 반영)

상태: 설계 (2026-07-01)

## 왜

지금 plan 그래프에서 `music` 노드는 hook/storyboard/narration보다 앞에 있다.

```
현재:  intake → reference_seed → product → character → environment
       → music → hook ⇄ storyboard(핑퐁) → narration → write_profile
```

그래서 `derive_music`은 스토리(storyboard·아크)와 나레이션(대사·delivery·강도)을 모르는 채,
레퍼런스 시드가 채운 훅(`style.hook`)만 보고 음악을 정한다. 문제:

- **볼륨감(prominence)이 나레이션과 무관하게 정해진다.** 나레이션이 정보를 촘촘히 실어
  나르는지, 감탄사 수준인지에 따라 BGM 존재감(→ execute의 bgm_gain)이 달라져야 하는데,
  그 신호를 음악이 못 본다.
- **장르·박자감·다이내믹스가 스토리와 어긋날 수 있다.** 스토리 아크(빌드/플랫)와 컷
  전개를 보고 골라야 하는데, 아직 storyboard가 없다.
- **훅 기반 SFX 판단이 확정 훅이 아니라 시드 훅에 근거한다.** 최종 훅은 hook⇄storyboard
  핑퐁 뒤에 정해지는데 음악은 그 전에 돈다.

의존성 확인: `hook`/`storyboard`/`narration` 노드 어디도 `state["music"]`을 읽지 않고,
`write_profile`만 소비한다. 따라서 music을 narration 뒤로 옮겨도 상류가 깨지지 않는다.

## 무엇을 (이번 스펙)

music을 plan의 **마지막 단계**(narration 다음, write 직전)로 옮기고, 스토리·나레이션을
입력으로 받아 음악을 결정한다.

```
변경:  intake → reference_seed → product → character → environment
       → hook ⇄ storyboard(핑퐁) → narration → music → write_profile
```

## 그래프 재배선 (`plan_graph.py`)

- `environment → music` 엣지를 `environment → hook`으로 바꾼다(music 건너뜀).
- `narration → write_profile` 엣지를 `narration → music`, `music → write_profile`로 바꾼다.
- hook⇄storyboard 핑퐁 조건 엣지와 노드 집합은 그대로. music 노드 등록도 그대로(위치만
  엣지로 바뀜).

## `derive_music` 입력 확장 (`music.py`)

시그니처에 선택 인자를 추가한다(기존 호출 호환 위해 전부 기본값 `None`):

```python
def derive_music(
    brief, product, tone, reference_music, text_client,
    character=None, pacing=None, hook=None,
    storyboard=None,        # 스토리 전개(패널·컷)
    narrative_arc=None,     # 서사 아크 라벨 리스트
    narration=None,         # NarrationSpec: 대사·delivery·voice(tone/pace)
) -> MusicSpec:
```

프롬프트(`_PROMPT`)에 두 블록을 추가한다:

- **스토리 블록**: storyboard 패널 요약(컷 수·전개)과 `narrative_arc`를 요약해 넣는다.
  "장르·리듬 필·다이내믹스를 이 스토리 전개에 맞춰 고르라"고 지시. build 아크면 상승
  컨투어(dynamics=build), 잔잔한 전개면 flat 쪽으로.
- **나레이션 블록**: 대사 줄 수/분량, `delivery`(voiceover/music_bed), voice tone/pace를
  넣는다. prominence 판단 기준을 명시: 나레이션이 정보를 촘촘히 나르면 `background`,
  대사가 최소·감탄사거나 music_bed면 `prominent`. (판단은 LLM이 한다 — 코드에서 강도
  점수를 계산해 강제하지 않는다. "노드별 LLM이 문맥으로 결정" 원칙 유지.)

나머지 계약은 유지:

- **tempo(bpm)는 여기서 정하지 않는다.** 음악은 "리듬 필"만 서술하고 실제 bpm은 execute가
  컷 리듬으로 맞추거나 레퍼런스 bpm을 쓴다. storyboard가 생겨도 이 분담은 그대로.
- **vocal=False 고정**(AI 보컬 배제), BGM은 인스트루멘털 베드.
- **폴백 경로 불변**: LLM 부재/실패 시 레퍼런스 음악 → 톤 첫 단어 무드 순으로 폴백.

## `_music_node` 갱신 (`plan_graph.py`)

`derive_music` 호출에 다음을 넘긴다:

- `hook=state["style"].hook` — 이제 핑퐁으로 **확정된** 최종 훅(이동 효과, 코드는 동일)
- `storyboard=state["storyboard"]`, `narrative_arc=state.get("narrative_arc")`
- `narration=state["narration"]`
- `pacing=state["style"].pacing`는 유지(스토리 요약과 별개로 편집 에너지 힌트)

## 볼륨감 연결 (변경 없음, 확인만)

`prominence`(background/prominent) → execute의 bgm 노드가 bgm_gain(덕킹/볼륨)으로 해소하는
배선은 이미 있다. music이 나레이션을 반영해 prominence를 더 정확히 정하면, "나레이션 강도 →
볼륨감"이 그 배선을 타고 자동으로 따라온다. 새로 배선할 것 없음.

## 테스트 (`tests/test_music.py`, `tests/test_plan_graph.py`)

LLM(text_client)은 모킹. 결정론 층만 실제 검증.

1. **derive_music 단위 테스트**(모킹 LLM)
   - narration이 촘촘한(대사 여러 줄, delivery=voiceover) 입력 + LLM이 background 응답
     → `prominence == "background"`
   - narration이 최소(대사 0~1줄 또는 delivery=music_bed) + LLM이 prominent 응답
     → `prominence == "prominent"`
   - 프롬프트에 storyboard/narration 요약이 실제로 주입됐는지(모킹 client가 받은 프롬프트
     문자열에 스토리·나레이션 신호가 포함) 검증
   - LLM 없음 → 레퍼런스 폴백, 레퍼런스도 없음 → 톤 무드 폴백(기존 동작 회귀)
2. **plan 그래프 순서 통합 테스트**
   - 그래프 실행 시 music 노드가 narration **뒤**에 돈다(트레이스 노드 순서 또는 music이
     최종 storyboard/narration을 받았는지로 확인). LLM은 모킹.
   - hook/storyboard/narration이 music 없이도 정상 실행(상류 비의존 회귀).

## 범위 밖

- prominence를 코드 점수로 강제하는 방식(이번엔 LLM 판단).
- bpm을 plan에서 확정(계속 execute가 컷 리듬으로 맞춤).
- execute 쪽 bgm_gain 계산식 변경(현행 유지).

## 관련 문서

- [../../../specs/workflows.md](../../../specs/workflows.md) — plan 그래프 노드·순서 정본(이 스펙으로 순서 갱신 대상)
- [../../../specs/similarity-loop.md](../../../specs/similarity-loop.md) — 음악 prominence/다이내믹스가 유사도 music 축과 연결
- [../../pipeline-design.md](../../pipeline-design.md) — 단계 설계 배경
