# 정보 스키마 (Information Schema)

상태: 확정(설계). 이 문서는 코어 그래프의 노드들이 주고받는 **모든 데이터 계약**을
정의한다. [workflows.md](workflows.md)의 짝꿍 문서다. 워크플로우가 "노드와 흐름"을
정하면, 이 문서가 "그 사이를 흐르는 데이터의 모양"을 정한다. 둘은 함께 읽는다.

코드 정본은 `src/reel_gen_agent/generate/schema.py`(생성)와
`src/reel_gen_agent/analysis/profile.py`(분석)다. 이 문서가 요구하는 모양과 코드가
어긋나면 **이 문서에 맞춰 코드를 고친다**(spec이 정본). 아래 "schema.py 조정 체크리스트"가
무엇을 바꿔야 하는지 명시한다.

## 원칙

- **스키마가 유일한 경계다([ADR.md](ADR.md) ADR-0003).** 분석과 생성, 기획과 생산은
  pydantic 스키마로만 통신한다. 백엔드를 갈아끼워도 스키마는 고정이다.
- **두 개의 최상위 산출물.**
  - **`ReelProfile`(profile.json)**: 기획의 동결 합본. 이식 가능한 *창작 의도*다.
    같은 ReelProfile은 유사한 영상을 만든다.
  - **`RunManifest`(run.json)**: 한 회차 실행 기록. 머신·리소스에 의존하는 *실행 결과*
    (`ProductionPlan`, 적용 폴백, 노드별 산출물)를 담는다.
- **이식 의도 vs 실행 계획 분리.** 자원 의존 결정(어떤 영상 모델, voice를 어떻게)은
  ReelProfile이 아니라 RunManifest의 ProductionPlan에 남는다. 그래야 profile이 이식된다.

## 그래프 엣지별 데이터 흐름

[workflows.md](workflows.md)의 노드 사이를 흐르는 스키마를 한눈에.

| 엣지(노드 -> 노드) | 흐르는 스키마 |
|---|---|
| intake -> concept | `Objective`, `AssetInput`(character/product), `reference_ref` |
| reference_analysis -> concept | `VideoProfile`(style_profile) |
| concept -> hook | `HookRequest` |
| concept -> 에셋/분석 노드 | `StyleDimensions`, `narrative_arc`, `ProductSpec` |
| concept -> environment | `StyleDimensions`, `narrative_arc` |
| hook -> storyboard | `HookSet`(채택 후보) |
| product_analysis -> product_assets | `ProductSpec.affordances` + 특징 |
| environment -> asset 게이트 | `EnvironmentSpec`(텍스트 + 선택 이미지) |
| asset 노드 -> storyboard | `AssetBible`(캐릭터/제품/환경, 필수 뷰 충족) |
| storyboard -> scripting | `Storyboard`, `StyleDimensions`, `ModelSpec`(캐릭터) |
| scripting -> profile_assembly | `NarrationSpec`, `MusicSpec`, 패널 `subtitle_text` |
| profile_assembly -> (confirm) | `ReelProfile` (= profile.json 동결) |
| production_planner -> 재료 노드 | `ProductionPlan` |
| 재료 노드 -> assemble | `Materials` |
| assemble -> verify | final.mp4 + `RunManifest` |
| verify -> repair_router | `ConformanceReport`(결함 카테고리) |
| verify -> describe | final.mp4(통과분) |
| describe -> evaluate | `UploadKit` (-> upload.md 렌더) |
| evaluate -> report | `RubricResult` |
| report -> finalize | `FinalReport` (-> report.md 렌더) |

`ConformanceReport`와 `RubricResult`의 계약은 [conformance-gate.md](conformance-gate.md),
[rubric.md](rubric.md)에 있다. 이 문서는 그 둘을 입력으로 받는 지점만 표시한다.

## 1. 그대로 재사용하는 기존 스키마

- **`InputMeta`**: 영상 포맷 메타와 가드레일. 정본은 [trd.md](trd.md) "영상 포맷 기본값과
  가드레일". 변경 없음. ReelProfile이 그대로 품는다.
- **`Storyboard` / `StoryboardPanel`**: 패널 목록. 패널 수/타이밍은 style_profile에서
  시딩. 소폭 확장(아래 3번)만, 구조는 유지.
- **`RunManifest` / `NodeRun`**: 실행 기록. 확장(아래 3번)해 ProductionPlan과 폴백,
  그리고 노드별 핵심 프롬프트 원문(`NodeRun.prompt`)을 담는다.

## 2. 신규 스키마

### Objective (영상 목적, 필수)

영상 생성의 필수 입력. 없으면 그래프 진입 불가.

| 필드 | 타입 | 의미 |
|---|---|---|
| `goal` | str | 이 영상이 이루려는 것(필수) |
| `video_type` | str \| None | 광고/언박싱/튜토리얼/후기 등 큰 갈래 |
| `target_audience` | str \| None | 주 시청자 |
| `key_message` | str \| None | 한 줄 핵심 메시지 |

### AssetInput (캐릭터/제품 입력)

캐릭터와 제품은 **기본적으로 있다고 가정**하되 없을 수 있다. 없음은 의도다.

| 필드 | 타입 | 의미 |
|---|---|---|
| `kind` | str | `character` / `product` |
| `source` | str \| None | 이미지 경로, URL, 또는 텍스트 묘사 |
| `present` | bool | 존재 여부. 기본 True 가정, 없으면 False |
| `absent_reason` | str \| None | 없을 때 왜 없는지(의도). 예: 제품 단독, 브랜드 무드 |

### StyleDimensions (다섯 가지 스타일 차원)

[workflows.md](workflows.md) concept 노드가 채운다. **기존 `StyleSpec`을 이 스키마로
대체·확장한다**(아래 3번).

**레퍼런스 시딩 범위.** 레퍼런스가 있으면 ReelProfile을 최대한 레퍼런스에서 생성한다.
분석된 `VideoProfile`(style_profile)이 다섯 차원만이 아니라 베이스라인 전체의 씨앗이다.
끌어오는 항목: 톤, 페이싱, 컷 리듬, 자막 스타일, 후크, 음악 스타일/다이내믹(MusicSpec),
내러티브 아크, 기본 스토리보드 구조. concept 노드가 이 베이스라인을 영상 목적·캐릭터·
제품에 맞춰 적응시킨다. 레퍼런스가 없으면 LLM이 목적에서 처음부터 제안한다. 출처는
`Provenance.style_source`(`reference`/`llm`)와 각 항목의 source 필드에 남긴다.

| 필드 | 타입 | 의미 |
|---|---|---|
| `tone` | list[str] | 톤. 예: 밝고 깨끗, 관능적 만족, 차분한 시연. 공통축은 긍정·일상·신뢰 |
| `pacing` | str | `fast_montage` / `slow_demo` / `mixed` |
| `cut_rhythm` | CutRhythm | 컷 리듬(아래) |
| `hook` | HookCandidate | 채택된 후크. hook 노드가 낸 `HookSet`에서 선택. 계약은 [hook-generator.md](hook-generator.md) |
| `subtitle` | SubtitleSpec | 자막 스타일(기존 재사용) |
| `palette` | list[str] | 색 팔레트 |
| `realism` | str | 기본 `hyper_realistic` |

#### CutRhythm

| 필드 | 타입 | 의미 |
|---|---|---|
| `basis` | str | `semantic_action`(의미·액션 기반) / `beat_sync`(음악 비트 동기) |
| `pattern` | str \| None | 예: 빠른 컷 구간과 롱홀드가 클러스터로 교차 |
| `source` | str | `reference`(style_profile.cut 시딩) / `llm` |

#### Hook 스키마는 hook-generator.md 소관

후크는 별도 `hook` 노드가 만든다([workflows.md](workflows.md)). 입출력 스키마
(`HookRequest`, `HookCandidate`, `HookSet`, `HookType`)와 유형 표, 선택 로직, 결정론
규칙은 [hook-generator.md](hook-generator.md)가 정본이다. 여기서 중복 정의하지 않는다.
`StyleDimensions.hook`은 그 `HookSet`에서 채택한 `HookCandidate` 하나를 가리킨다.
배경·예시는 [../docs/hook-insight.md](../docs/hook-insight.md).

### EnvironmentSpec (배경·촬영 환경)

environment 노드가 영상 컨셉·스토리보드에 맞춰 정의한다. **텍스트 정의는 항상 채운다.**
이미지는 텍스트만으로 일관성이 부족할 때만 생성한다(캐릭터·제품처럼 잠금 에셋).

| 필드 | 타입 | 의미 |
|---|---|---|
| `location` | str | 장소(예: 실내 침실, 욕실 세면대, 카페) |
| `setting` | str \| None | 세트·배경 구성 묘사 |
| `lighting` | str \| None | 조명(자연광, 링라이트, 따뜻/차가운) |
| `time_of_day` | str \| None | 시간대(아침/저녁 등) |
| `mood` | str \| None | 공간 무드 |
| `props` | list[str] | 배경 소품 |
| `needs_image` | bool | 환경 레퍼런스 이미지 생성 여부(노드 판단) |
| `reference_image` | str \| None | 생성했으면 이미지 경로 |

### NarrationSpec (대사 스크립트 + 전달 방식)

scripting 노드가 만든다. **voice는 되도록 사용하되 기본 전달은 나레이션(`voiceover`)이다**
([ADR.md](ADR.md) ADR-0012). `delivery`가 ProductionPlan의 voice_strategy로 해소된다
(voiceover->separate_tts, on_camera->integrated, none->none).

| 필드 | 타입 | 의미 |
|---|---|---|
| `delivery` | str | `voiceover`(화면과 분리된 TTS 나레이션, **기본**) / `on_camera`(영상 모델 네이티브 발화, 필요할 때만) / `none`(음악 베드만) |
| `lines` | list[NarrationLine] | 패널별 대사 |
| `voice` | VoiceSpec | **캐릭터(`ModelSpec`)에서 유도한 voice 속성(매우 중요)** |
| `language` | str | 대사 언어 |
| `text_model` | str \| None | 대사 생성에 쓴 LLM(Claude/Gemini) |

voiceover는 언어(한국어/영어) 무관 ElevenLabs `eleven_v3`가 기본이고(없을 때만 Google TTS
3.1 preview 폴백) 캐릭터 음색을 길게 연속 생성한다(컷이
나뉘어도 톤 일관). on_camera는 역동적 발화가 필요한 컷에서만, 멀티컷+립싱크 일관이 필요하면
Kling O3 Pro reference-to-video로만 가능하다(ai-model-records.md 4·6번). voice를 먼저 만들어
영상 모델에 주입하는 립싱크는 쓰지 않는다.

#### NarrationLine

| 필드 | 타입 | 의미 |
|---|---|---|
| `panel_index` | int | 대응 패널 |
| `text` | str | 그 패널 대사 |

> `VoiceSpec`(기존)은 성별·나이·룩·분위기 같은 `ModelSpec` 캐릭터 설정에서 유도해 채운다.
> 음색·딕션·억양이 캐릭터와 맞아야 한다. `on_camera`면 영상 모델이 그 캐릭터로 말하고,
> `voiceover`여도 TTS 음색을 캐릭터에 맞춘다. 대사와 캐릭터 매칭 voice가 패널 타이밍에
> 붙는 정렬은 assemble가 보장한다([workflows.md](workflows.md)).

> `MusicSpec`(기존)은 scripting의 음악 정의가 채운다. 기존 `mood`/`dynamics`에 더해
> `style`/`type`/`tempo`(컷 리듬 정렬)를 둔다(아래 3번 확장). 실제 BGM 생성은 production.

### Provenance (출처·재현)

| 필드 | 타입 | 의미 |
|---|---|---|
| `style_source` | str | `reference` / `llm` |
| `reference_ref` | str \| None | 레퍼런스 영상/URL |
| `seeds` | dict | 결정론 재현용 시드(컷 타이밍, 조립 등) |
| `text_model` | str \| None | 기획·카피에 쓴 LLM |
| `schema_version` | str | ReelProfile 스키마 버전 |

### ProductionIntent (이식 가능한 생산 의도)

*원하는 바*만 담는다. 실제 해소는 ProductionPlan. `auto`는 planner에 위임.

| 필드 | 타입 | 의미 |
|---|---|---|
| `voice_pref` | str | `NarrationSpec.delivery`를 미러: `on_camera` / `voiceover` / `none` / `auto`. 기본은 voice 사용(auto는 가능하면 켬) |
| `multishot_pref` | str | `prefer` / `avoid` / `auto` |
| `key_image_per_cut_pref` | str | `prefer` / `avoid` / `auto` |
| `shot_renderer_pref` | str | `i2v` / `ken_burns` / `canvas` / `auto` |
| `bgm_pref` | str | `gen` / `file` / `none` |
| `sfx_pref` | bool | 효과음 사용 선호 |

### ReelProfile (동결 합본, profile.json)

기획의 모든 부산물을 조립한 최상위 산출물. 같은 ReelProfile -> 유사 영상.

| 필드 | 타입 | 의미 |
|---|---|---|
| `schema_version` | str | 버전 |
| `meta` | InputMeta | 포맷 메타(재사용) |
| `objective` | Objective | 영상 목적 |
| `product` | ProductSpec | 제품(affordances 포함, 아래 3번) |
| `character` | ModelSpec | 캐릭터(기존 ModelSpec 재사용) |
| `style` | StyleDimensions | 다섯 스타일 차원 |
| `narrative_arc` | list[str] | 이름 있는 템플릿 |
| `asset_bible` | AssetBible | 캐릭터/제품/환경 에셋(필수 뷰 + EnvironmentSpec 포함) |
| `storyboard` | Storyboard | 패널 + 콘티 |
| `narration` | NarrationSpec | 대사 스크립트 + 전달 방식 + 캐릭터 매칭 voice |
| `music` | MusicSpec | 음악 정의(스타일/유형/무드/다이내믹스/템포) |
| `production_intent` | ProductionIntent | 이식 가능한 생산 의도 |
| `provenance` | Provenance | 출처·시드 |
| `watermark` | str \| None | 워터마크 |

> 비고: 기존 `GenerationInput`은 ReelProfile의 *부분집합*(prompt/objective/meta/product/character/style/
> style_prompt/voice/music/subtitle/narrative_arc)에 해당한다. `prompt`는 `run "..."`과 같은
> 자유 자연어 요청으로 먼저 보존한다. `product.url`은 수동 입력
> 템플릿에서 제품 페이지 근거를 보존하기 위한 필드고, `product.path`는 Product asset 생성에
> 반드시 넣을 로컬 제품 이미지 참조 경로다. `model.path`는 Character asset 생성에 반드시 넣을
> 로컬 모델/캐릭터 이미지 참조 경로다. ReelProfile 도입 후 GenerationInput은
> ReelProfile로 흡수하거나, 호환을 위해 ReelProfile에서 파생하는 얇은 뷰로 남긴다
> (아래 3번에서 택1).

### ProductionPlan (런타임 해소, RunManifest에 기록)

ProductionIntent를 가용 리소스와 모델 능력에 맞춰 해소한 결과. **ReelProfile이 아니라
RunManifest에 둔다.**

| 필드 | 타입 | 의미 |
|---|---|---|
| `video_model` | str | 선택된 영상 모델 ID |
| `capability` | ModelCapability | 그 모델의 능력 |
| `voice_strategy` | str | `integrated` / `separate_tts` / `none` |
| `multishot` | bool | 한 번에 멀티샷 vs 샷별 concat |
| `key_image_per_cut` | bool | 컷별 핵심 스틸 별도 생성 |
| `panel_renderers` | list[str] | 패널별 `i2v` / `ken_burns` / `canvas` |
| `bgm` | str | `gen` / `file` / `none` |
| `sfx` | bool | 효과음 |
| `fallbacks_applied` | list[str] | 적용한 폴백(예: 영상 키 없음 -> ken_burns) |

### ModelCapability (capability matrix 항목)

모델별 능력 데이터. **코드에 모델을 박지 않고 config/.env 데이터로 둔다.**

| 필드 | 타입 | 의미 |
|---|---|---|
| `model_id` | str | 모델 ID |
| `lane` | str | `vertex` / `fal` / `local` |
| `multishot` | bool | 멀티샷 한 번에 지원 |
| `integrated_voice` | bool | 영상+voice 동시 생성 지원 |
| `max_clip_sec` | float | 한 클립 최대 길이 |
| `max_resolution` | str | 최대 해상도(예: 1080x1920) |

### Materials (생성 재료 모음)

병렬 재료 노드가 채우고 assemble가 소비.

| 필드 | 타입 | 의미 |
|---|---|---|
| `key_images` | list[str] | 컷별 핵심 스틸(선택) |
| `shot_clips` | list[str] | 패널별 클립(concat 순서) |
| `voice_audio` | str \| None | 보이스 트랙 |
| `bgm_audio` | str \| None | 배경 음악 |
| `sfx_audio` | list[str] | 효과음 |
| `subtitle_pngs` | list[str] | pilmoji 투명 자막 PNG |

### UploadKit (업로드용 자산)

describe 노드가 verify 통과 후 만든다. 영상을 그대로 올릴 때 쓴다. `upload.md`로 렌더한다.
출처는 `ReelProfile`(목적·후크·제품·스토리보드)과 final.mp4.

| 필드 | 타입 | 의미 |
|---|---|---|
| `title` | str | 업로드용 영상 제목 |
| `outline` | list[OutlineItem] | 간단한 영상 구조(분초 단위) |
| `caption` | str | 본문 멘트. 컨셉에 맞춰 짧게 또는 자세히, **제품명 포함** |
| `hashtags` | list[str] | 업로드용 해시태그(선택) |

#### OutlineItem

| 필드 | 타입 | 의미 |
|---|---|---|
| `timecode` | str | `mm:ss` |
| `content` | str | 그 구간 주요 내용 |

### FinalReport (최종 결과 리포트)

report 노드가 이번 회차를 한 장으로 묶은 산출물. `report.md`는 이 스키마에서 렌더링한다
(렌더링은 결정론, `final_opinion`과 `viral_prediction`만 LLM 생성). 데이터 출처는
`ReelProfile`, `RunManifest`(ProductionPlan 포함), `RubricResult`, `ConformanceReport`.

| 필드 | 타입 | 의미 |
|---|---|---|
| `run_id` | str | 회차 식별자 |
| `user_input` | UserInputEcho | **앞단에 싣는 원본 유저 입력**(아래). 무슨 입력이 이 결과를 냈는지 |
| `node_prompts` | list[NodePrompt] | **노드별 핵심 프롬프트 원문**(아래). 어떤 프롬프트가 무엇을 만들었는지 |
| `final_opinion` | str | 결과 영상에 대한 종합 최종 의견(LLM) |
| `node_flow` | list[str] | 생성에 쓰인 노드 그래프 흐름(`RunManifest.nodes` 순서) |
| `models_used` | dict | 용도별 사용 모델: 텍스트/이미지/영상/저지 모델 ID와 lane |
| `bgm_source` | BgmReport | BGM 출처와 모델(아래) |
| `conformance` | dict | conformance pass 여부와 체크 요약(`ConformanceReport`에서) |
| `rubric` | dict | rubric gated/flat 점수와 D1~D7(`RubricResult`에서) |
| `viral_prediction` | str | 바이럴 효과 예측. 후크·완시청(D1·D2) 근거의 LLM 서술 |
| `report_md` | str | 렌더된 마크다운 경로(`outputs/<run_id>/report.md`) |

report.md 레이아웃은 **유저 입력(앞단)** -> 최종 의견 -> 노드 흐름 -> 사용 모델 -> BGM ->
eval 점수 -> 바이럴 예측 -> **노드별 핵심 프롬프트 원문** 순으로 싣는다.

#### UserInputEcho

원본 유저 입력을 그대로 되비춘다. 출처는 `ReelProfile.objective`와 입력 셋.

| 필드 | 타입 | 의미 |
|---|---|---|
| `objective` | str | 영상 목적(원문) |
| `character_input` | str \| None | 캐릭터 입력 원본(경로/URL/묘사). 없으면 `absent_reason` |
| `product_input` | str \| None | 제품 입력 원본. 없으면 `absent_reason` |
| `reference_ref` | str \| None | 레퍼런스 영상/URL |
| `raw_brief` | str \| None | 텍스트 브리프로 들어온 경우 원문 그대로 |

#### NodePrompt

노드가 외부 모델에 보낸 핵심 프롬프트 텍스트 원본. 출처는 `RunManifest.nodes[].prompt`.

| 필드 | 타입 | 의미 |
|---|---|---|
| `node` | str | 노드 이름(concept / asset_bible / storyboard / video_shots ...) |
| `prompt` | str | 그 노드의 핵심 프롬프트 원문 |
| `model` | str \| None | 그 프롬프트를 받은 모델 ID |

#### BgmReport

| 필드 | 타입 | 의미 |
|---|---|---|
| `kind` | str | `gen` / `file` / `none` |
| `model` | str \| None | 생성이면 모델 ID(예: Lyria) |
| `source` | str \| None | 제공 파일이면 그 경로/출처 |

## 3. 기존 스키마 변경 (schema.py 조정 체크리스트)

이 기획에 맞추려면 `generate/schema.py`를 아래대로 고친다. 한 번에 하나씩, 테스트와 함께.

1. **`StyleSpec` -> `StyleDimensions`로 대체·확장.** 기존 `tone/pacing/cut_mode/palette/
   realism`를 유지하되 `cut_mode`를 `CutRhythm`으로 승격하고 `hook`(Hook), `subtitle`
   (SubtitleSpec)을 품는다. 다섯 차원을 한 곳에 모은다.
2. **후크 스키마는 hook-generator.md 소관.** `HookRequest`/`HookCandidate`/`HookSet`/
   `HookType`을 [hook-generator.md](hook-generator.md) 완료 기준대로 `generate/schema.py`에
   정의하고 진입 함수는 `generate/hook.py::generate_hooks`. `StyleDimensions.hook`은
   채택된 `HookCandidate`를 참조한다(여기서 별도 Hook 스키마를 만들지 않는다).
3. **`CutRhythm` 신규.** basis/pattern/source.
4. **`ProductSpec`에 `affordances: list[str]` 추가.** pipeline-design의 affordance
   추출 결과를 싣는다.
5. **`CharacterProfile`·`ProductProfile`에 필수 뷰 체크리스트 추가.** 단일 `sheet_image`
   에 더해 `views: list[AssetView]`(name, required, image, satisfied)를 둔다. 캐릭터 필수
   뷰: 얼굴 클로즈업, 표정 변화, 전신, 좌/우 얼굴. 제품 필수 뷰: 정면, 좌우/위, 박스 안,
   특수 기능. 게이트가 `satisfied`로 충족을 검증한다.
5b. **`AssetBible`에 `environment: EnvironmentSpec` 추가.** 캐릭터·제품과 함께 환경을
   잠금 에셋으로 둔다. EnvironmentSpec은 텍스트 정의 필수, 이미지는 `needs_image`일 때만.
6. **`Objective`, `AssetInput`, `EnvironmentSpec`, `NarrationSpec`, `NarrationLine`,
   `Provenance`, `ProductionIntent`, `ReelProfile` 신규.** ReelProfile의 voice 필드는
   `narration: NarrationSpec`로 둔다(VoiceSpec은 NarrationSpec 안).
7. **`ProductionPlan`, `ModelCapability`, `Materials`, `UploadKit`, `OutlineItem`,
   `FinalReport`, `BgmReport`, `UserInputEcho`, `NodePrompt` 신규.** ProductionPlan은
   `RunManifest`에 필드로 단다
   (`production_plan: ProductionPlan | None`, `fallbacks_applied`는 ProductionPlan 안).
   FinalReport는 report 노드 산출이고 report.md로 렌더된다.
10. **`NodeRun`에 `prompt: str | None` 추가.** 각 노드가 외부 모델에 보낸 핵심 프롬프트
    원문을 남긴다. report 노드의 `node_prompts`가 이걸 모은다. 키·토큰은 레다크션하되
    프롬프트 본문은 남긴다([logging-strategy.md](logging-strategy.md) 보안 규칙).
11. **`MusicSpec` 확장, `VoiceSpec` 유도 규칙.** MusicSpec에 `style`/`type`/`tempo`를
    더한다(기존 mood/dynamics 유지). VoiceSpec은 `ModelSpec`(캐릭터)에서 음색·딕션·억양을
    유도해 채운다(코드가 캐릭터 설정을 voice 파라미터로 매핑). 둘 다 scripting 노드가 채운다.
8. **`StoryboardPanel`에 `key_image: str | None`, `renderer: str | None`,
   `environment_lock: bool` 추가(선택).** renderer는 ProductionPlan.panel_renderers와,
   environment_lock은 AssetBible.environment 참조와 정렬한다.
9. **`GenerationInput` 처리(택1).** (a) ReelProfile로 흡수하고 GenerationInput 제거,
   또는 (b) 호환을 위해 ReelProfile에서 파생하는 얇은 뷰로 남긴다. 워킹 스켈레톤이
   손으로 쓴 generation_input.json에서 출발하므로, 당장은 (b)로 두고 기획 페이즈가
   붙을 때 (a)로 수렴한다.

## 4. 검증과 가드레일

- **포맷 가드레일**은 `InputMeta`의 밸리데이터가 강제한다(9:16, 1080p 상한, 1~60초,
  fps {24,25,30,50,60}). 정본은 [trd.md](trd.md). ReelProfile은 이를 그대로 상속한다.
- **필수 뷰 충족**은 asset_bible 게이트에서 `AssetView.satisfied`로 검증한다. 미충족이면
  게이트가 재생성을 요구한다.
- **conformance**는 final.mp4가 ReelProfile/Storyboard/RunManifest와 합치하는지를
  하드로 검증한다(머지 무결성, 템플릿 적합성). 계약은 [conformance-gate.md](conformance-gate.md).

## 5. 재현성

같은 `ReelProfile`은 유사한 영상을 만든다. `Provenance.seeds`로 결정론 부분(컷 타이밍,
조립)을 재현한다. 후크는 설계상 비결정적이라 완전 동일이 아니라 유사를 보장한다.
`ProductionPlan`은 머신마다 갈릴 수 있으므로 `fallbacks_applied`로 차이를 추적한다.

**출력 폴더 구조.** 회차 산출물은 `outputs/<run_id>/`에 보존하고, `run_id`는
`간단제목축약-생성일시` 형태다(예: `glow-serum-reel-20260630-204512`). plan이 이 폴더를
만들고 ReelProfile을 `ReelProfile-{핵심컨셉}-{생성일시}.json`으로 쓴다(컨셉 슬러그·일시는
run_id와 같은 값). execute가 같은 폴더에 영상과 산출물을 채운다.

폴더 안 핵심 산출물 3종은 `final.mp4`(영상), `report.md`(FinalReport 렌더),
`upload.md`(UploadKit 렌더)이고, 기획 산출물 `ReelProfile-{컨셉}-{일시}.json`과 재현용
부산물 `run.json`(RunManifest), `assets/`, `storyboard/`, `panels/`를 함께 둔다.
`RunManifest.run_id`와 폴더명은 같다.
