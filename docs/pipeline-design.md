# 생성 파이프라인 설계

상태: 설계 완료, 아직 구현 전. 이 문서는 앞으로의 구현이 따라야 할 계약서다. 분석 계층
(`analyze`)은 이미 만들어져 있고, 아래 생성 단계들은 아직이다.

## 형태

```
generation_input.json
   ▼ [gate: concept]
asset bible (character + product images)
   ▼ [gate: asset_bible]   <- 필수
storyboard.json + panel stills
   ▼ [gate: storyboard]    <- 비싼 영상 단계 전에 승인
video (image-to-video per panel + ffmpeg assembly)
   ▼ [gate: video]
Gate: profile(output) vs style_profile (유사도 점수)
```

각 단계는 노드 하나에 확인 인터럽트가 뒤따른다. 에셋 바이블이 캐릭터와 제품 룩을 먼저
고정하므로, 이후 모든 단계가 일관성을 유지한다. 스토리보드 게이트가 있는 이유는 영상
단계가 비싸기 때문이다. image-to-video에 돈을 쓰기 전에 스틸을 먼저 승인한다.

## 휴먼 인 더 루프 게이트

중요한 단계는 모두 확인을 거칠 수 있다. 게이트는 세 가지 중 하나로 동작한다.

- **ask**(기본, 챗 모드): 결과를 보여주고 사용자가 확인하거나 수정한다.
- **pass**(`--force-step-pass <step>`, 또는 CLI 안에서 `/pass <step>`): 프롬프트를
  건너뛰고 계속 진행한다.
- **런 모드**: 모든 게이트를 통과시키고 입력에서 바로 영상까지 생성한다.

이렇게 인터랙티브 리뷰를 게이트 설정으로 일반화하면, 그것이 곧 비인터랙티브 런 모드
(입력 넣으면 영상 나오고 프롬프트 없음)의 토대가 된다.

## 스키마

`src/reel_gen_agent/generate/schema.py`에 정의한다. 단계 사이의 안정적인 인터페이스다.

- `GenerationInput` — `objective`, `meta`(duration, aspect_ratio, fps, platform,
  language), `product`(name/url/description), `model`, `style`, `style_prompt`,
  `voice`, `music`, `subtitle`, `narrative_arc`, `watermark`, `style_profile_ref`.
  입력 파일은 이 스키마를 우선 검증하되, 깨진 JSON·메모·자연어 파일이면 텍스트 LLM이 목적,
  제품, 제품 URL, 캐릭터, 스타일, 언어를 라벨 브리프로 정규화한 뒤 같은 plan 그래프로 보낸다.
- `AssetBible` — `CharacterProfile`(시트 이미지 + 키 샷)과 `ProductProfile`(시트
  이미지 + 히어로 샷). 에셋당 멀티뷰 시트 이미지 하나면 충분하다. 이미지 모델이 한
  이미지 안에 여러 뷰를 렌더링하기 때문이다.
- `Storyboard` — 공통 `global_prompt`(캐릭터, 제품, 컬러, 무드처럼 모든 샷에 흐르는
  맥락)와 `StoryboardPanel`의 리스트로 나뉜다. 패널은 `index`, `beat`, `t_start`,
  `t_end`, `shot_type`, `camera`, `subject_lock`, `product_lock`,
  `local_prompt`(이 샷의 동작/카메라/표정), `subtitle_text`, `cta_text`,
  `still_image`. 패널 프롬프트는 렌더링 시 `global_prompt` + `local_prompt`로 합친다.
  공통부를 한 곳에 두면 캐릭터와 제품 일관성을 잡기 쉽다.

`narrative_arc`는 자유 텍스트가 아니라 이름 있는 템플릿이다(아래 "컨셉 템플릿" 참고).
`product`에는 추출된 `affordances`(제품이 가능케 하는 행동 목록)를 담아 스토리보드가
사용 장면을 짤 때 끌어 쓴다.

## 프로파일에서 스토리보드 씨앗 뽑기

패널 수와 패널별 타이밍은 `style_profile.json`의 분석된 컷 데이터에서 온다(입력의
`style_profile_ref`). 빠른 컷 13개짜리 레퍼런스는 짧은 패널 13개를, 느린 컷 5개짜리는
긴 패널 5개를 만든다. 편집 리듬을 상수가 아니라 파라미터로 재현한다.

## 컨셉 템플릿

`narrative_arc`는 이름 있는 템플릿 세트다(UGC, before/after, 튜토리얼, 언박싱, 셀피
후기, 직접 카메라 설명, 오버사이즈 제품 모먼트 등). 각 템플릿은 비트 구성과 샷 구성
규칙을 갖고, 일부는 특수 규칙을 가진다. 예를 들어 오버사이즈 모먼트 템플릿은 적어도 한
샷에서 제품을 비현실적으로 크게 잡는다. 스토리보드 생성기는 선택된 템플릿의 규칙을 읽어
패널의 beat와 shot_type을 채운다. 컷 수와 타이밍은 앞서대로 `style_profile`에서 오므로,
템플릿(무엇을 보여줄지)과 리듬(얼마나 빠르게)이 독립적으로 결합된다.

## 제품 affordance 추출

스토리보드 앞에 작은 단계를 둔다. 제품 이미지나 설명에서 가능한 행동을 먼저 뽑는다
(컵은 들고 마신다와 테이블에 둔다, 스프레이는 흔든다와 뿌린다, 가방은 메고 걷는다와
넣고 꺼낸다). 이 `affordances` 목록을 `product`에 실어 스토리보드 생성기가 샷
디스크립션에 끌어 넣는다. affordance를 강제로 주입하면 "그럴듯한 사용 장면"이 자연스럽게
나오고, 영상이 실제 존재하는 제품처럼 보여 설득력이 올라간다.

## 소셜 미디어 플랫폼 제약 자동 삽입

대상 플랫폼마다 사전 제약이 있다. 영상을 만들 때 이 제약을 프롬프트에 자동으로 끼워
넣어야 한다. 특히 **스토리보드 생성 단계**에서 패널 프롬프트와 자막/CTA 배치에 반드시
반영한다. 사용자가 매번 손으로 적게 두지 않는다.

제약은 입력의 `meta.platform`(과 `meta.aspect_ratio`, `meta.duration`)에서 끌어와,
플랫폼별 룩업 테이블로 펼친다. 다루는 항목:

- **종횡비와 해상도**: 세로 9:16 고정. 패널 프롬프트의 프레이밍 지시에 박는다.
- **길이 상한**: 플랫폼별 권장/최대 길이(예: 쇼츠 60초 이하). 패널 타이밍 합이 이를
  넘지 않도록 스토리보드 단계에서 잘라낸다.
- **세이프 존**: 플랫폼 UI(우측 버튼 열, 하단 캡션/계정 바)가 가리는 영역. 자막과
  CTA, 핵심 피사체를 그 바깥에 두도록 패널 프롬프트의 구도와 자막 위치에 반영한다.
- **자막 가독성**: 최소 글자 크기, 외곽선/그림자 대비 등 안전 규칙.
- **콘텐츠 정책**: 워터마크 처리, 금지 표현 등 플랫폼 정책에서 오는 제약.

이 제약들을 스토리보드 생성 프롬프트에 자동 주입하면, 같은 입력이라도 대상 플랫폼이
바뀌면 구도와 자막 배치가 그에 맞게 달라진다. 플랫폼 규칙도 하드코딩이 아니라
`meta.platform`으로 구동되는 데이터다.

## 이미지, 영상 백엔드

- **이미지**(에셋 시트와 패널 스틸): Gemini 이미지 모델(`GEMINI_IMAGE_MODEL`, 기본
  `gemini-3.1-flash-image`). 스틸 퀄리티가 영상 퀄리티를 좌우하므로 품질을 우선한다.
  패널 스틸은 일관성을 위해 캐릭터와 제품 레퍼런스 이미지를 함께 넘긴다. 더 상위 이미지
  모델은 나중 선택지다.
- **영상**: 패널별 image-to-video(`VEO_MODEL`의 Vertex lane 우선, `GEMINI_VEO_MODEL`
  폴백), 이어서 ffmpeg concat, 자막 오버레이
  (아래 참고), 배경 음악 mux(`LYRIA_MODEL` 또는 제공된 음악), 워터마크.
- **멀티샷 분할**: 영상 모델은 보통 한 번에 짧은 길이(예: 약 15초)만 만든다. 목표 길이가
  그보다 길면 패널을 모델 한계에 맞게 쪼개 생성한 뒤 ffmpeg로 이어 붙이고 트랜지션을
  넣는다. 모델과 콘티에 따라 한 번에 멀티샷을 호출할지 샷별로 짧게 뽑아 concat할지
  고른다. 모델별 클립 길이 한계는 백엔드 설정값으로 둔다.
- **저비용 폴백**(Stage C 설정): 영상 모델을 끄면, 스틸을 켄 번스 모션으로 같은 조립
  경로에 태워 렌더링한다. 영상 모델 예산 없이도 시스템이 끝까지 돈다.

## 게이트 채점과 품질 검사

마지막 게이트는 유사도 채점에서 그치지 않는다. 먼저 conformance가 하드 pass/fail로
막아서고, 통과한 것만 아래 채점으로 넘어간다.

- **결과물 무결성·적합성(Conformance, 하드 pass/fail)**: 의도한 템플릿대로 기술적으로 온전히
  만들어졌고 노드 산출물이 빠짐없이 머지됐는지를 본다. 미디어 무결성, 템플릿 적합성, 노드/머지
  무결성, 볼륨, 자막 위치·효과, 컷 전환을 결정론과 VLM으로 검사한다. fail이면 아래 채점으로
  가지 않고 약한 샷을 재생성한다. 계약은 [../specs/conformance-gate.md](../specs/conformance-gate.md).
- **스타일 유사도**: 생성물을 분석기로 다시 프로파일링해 `style_profile`과 비교 채점한다
  (닫힌 루프). 분석기가 프로파일러이자 채점기로 같은 잣대를 쓴다.
- **콘텐츠 효과성(드라이버 Rubric)**: 닮았는지와 별개로, 이 영상이 스크롤을 멈추게 하고
  끝까지 보게 하고 행동을 끌어내는지를 7개 차원으로 채점한다. D1·D2(후크·완시청)는 곱셈
  게이트, D3~D7은 가중합 코어다. `passed`를 게이트 신호로 쓴다. 같은 자로 레퍼런스도
  채점해 기준선을 잡는다. 계약은 [../specs/rubric.md](../specs/rubric.md), 배경은
  [rubric.md](rubric.md)를 본다.
- **품질/안전 검사**: 생성된 클립을 멀티모달 모델로 검사해 제품이 제대로 나왔는지(색,
  형태, 브랜드 훼손 여부), 캐릭터가 프로필과 맞는지, 위험 요소(민감 표현, 저작권, 로고
  문제)가 없는지 확인한다.

문제가 발견되면 전체를 다시 만들지 않는다. **해당 샷만 재생성**하고 그 샷의 프롬프트를
자동 보정한다(로고 노출 축소, 자막 위치 조정 등). 패널 단위로 스토리보드를 들고 있으니
샷 단위 재생성이 자연스럽고, 영상 모델 비용도 아낀다.

## 자막과 이모지

자막의 이모지(반짝임, 하트, 광채 마크)는 이 영역에서 훅의 일부라, 컬러 이모지가 제대로
렌더링돼야 한다. 흔한 두 경로는 이걸 잘 못 다룬다.

- libass를 통한 ffmpeg ASS 번인은 컬러 이모지 지원이 빈약하다(COLR/CBDT 폰트가 흑백
  글리프나 두부(tofu)로 나온다).
- 순수 Pillow는 자동 폰트 폴백이 없어서, 문자열을 텍스트와 이모지 구간으로 직접
  쪼개야만 라틴/한글 텍스트와 이모지를 함께 그린다.

방법: 자막 줄마다 **Pillow 위에 pilmoji**로 투명 PNG를 렌더링하고(Noto Color Emoji나
Twemoji 같은 번들 컬러 세트에서 이모지를 합성), 그 PNG를 패널 타이밍에 맞춰 ffmpeg로
영상에 오버레이한다. 이러면 컬러 이모지가 그대로 살고, 폰트와 외곽선과 위치를 완전히
통제할 수 있으며, 무거운 시스템 의존성도 더하지 않는다(pycairo/Pango 스택은 cairo,
pango 시스템 라이브러리와 설치 마찰을 더한다). 순수 Pillow가 손으로 해야 했던
텍스트/이모지 구간 분리도 pilmoji가 처리한다.

자막 텍스트와 타이밍은 스토리보드 패널에서 오므로, 음성 인식이나 강제 정렬이 필요 없다.
pycairo/Pango는 복잡한 텍스트 셰이핑이 정말 필요해질 때를 대비한 폴백으로만 남긴다.

## 모듈 레이아웃(만들 것)

```
src/reel_gen_agent/generate/
  schema.py        # 있음
  asset_bible.py   # 이미지 모델 -> 캐릭터 + 제품 에셋
  affordances.py   # 제품 이미지/설명 -> 가능한 행동 목록
  templates.py     # 컨셉 템플릿(narrative_arc) 정의와 샷 구성 규칙
  storyboard.py    # 입력 + style_profile + 템플릿 + affordance -> storyboard.json -> 패널 스틸
  subtitles.py     # pilmoji -> 투명 자막 PNG (컬러 이모지 보존)
  video.py         # 패널별 image-to-video + 멀티샷 분할 + ffmpeg 조립 (자막 오버레이, 켄 번스 폴백)
  quality.py       # 생성물 VLM 품질/안전 검사 -> 샷 단위 재생성 신호
  gates.py         # GateConfig + 확인 / 수정 / 통과 로직
  graph.py         # 노드 + 인터럽트 배선
outputs/<run_id>/  # generation_input.json, assets/, storyboard/, panels/, final.mp4
```

## 첫 구현 범위 (워킹 스켈레톤)

다듬기 전에 거친 영상 하나를 끝까지 돌린다.

1. 손으로 작성한 `generation_input.json`에서 시작한다(컨셉 LLM 단계는 나중에).
2. asset bible -> [gate] -> 스토리보드 JSON과 스틸 -> [gate] -> image-to-video ->
   조립된 mp4 -> [gate].
3. 게이트 프레임워크(ask/pass, `--force-step-pass`, 챗/런 모드)를 포함한다.

이러면 게이트, 에셋 바이블, 스토리보드를 모두 돌려보면서 완성된 영상이 나온다. 전체
컨셉, 템플릿 단계는 그다음이다.

## Replan (rerun)

`rerun`(1-level 커맨드)은 동결된 ReelProfile을 다시 접근한다. 목적, 제품, 모델은 그대로 두고
(정체성 에셋은 재사용), 레퍼런스를 무시하고 style부터 재생성한 뒤 그 style로 서사(훅 <->
스토리보드, 내레이션, 음악)를 다시 굴리고, key_visual을 재생성하고, 새
`ReelProfile-<new-keyword>.json`을 새 run 폴더에 써서 production에 넘긴다. 예전 `execute
--replan` 플래그를 대체한다(프로필을 그대로 렌더하는 execute와 서사를 다시 뽑는 작업은 별개).
자세한 내용은 [specs/replan.md](../specs/replan.md)를 본다.

## 보이스오버 (선택)

기본은 꺼짐. 주 경로는 뮤직 베드 더하기 자막이다. 데모용으로 켤 때는 감정 태그를 단
text-to-speech(예: `[curious] ... [cheerfully] ...`)를 써서 전달이 비트에 맞도록 한다.
