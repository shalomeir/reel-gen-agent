# AI 모델 기록 (ai-model-records.md)

상태: 확정, 갱신형. 이 문서는 용도마다 **어떤 모델을 왜 골랐는지**를 기록한다. 코드와
[trd.md](trd.md)는 특정 모델에 묶이지 않는다. 실제 모델 ID는 `.env`로 주입하고 어댑터가
읽는다. 이 문서는 그 선택의 근거와 이력이다. 모델을 바꾸면 여기를 먼저 고치고 `.env`에
반영한다.

## 표기 규칙

- **1차**: 기본으로 호출하는 모델.
- **폴백**: 1차가 막히거나(키 없음, 한도, 장애) 품질이 모자랄 때 대신 쓰는 모델.
- **홀딩**: 검토했으나 지금은 안 쓰기로 한 것. 제외 이유나 "적용해 봤지만 안 쓰기로 한"
  이유를 같이 적는다.

원칙: 레포의 단일 필수 키 약속(`GEMINI_API_KEY` 하나로 분석과 이미지 생성)을 지킨다.
다만 GCP 자격이 있으면 분석과 멀티모달 호출은 `GENAI_BACKEND=auto` 규칙에 따라 Vertex
lane을 우선해 Google Cloud 크레딧을 쓰고, 단일 키는 폴백으로 보장한다(상세는 trd.md).
그래서 가능한 용도는 Gemini 계열을 1차로 두고, 다른 키가 필요한 모델은 옵션 폴백이나
업그레이드로 둔다. 예외는 기획·카피 생성 텍스트 레인이다(아래 2번). 여기는 카피 품질이
결과를 좌우해 Gemini 3.1 Pro와 Claude Opus를 일급으로 비교한다. 두 키가 이미 `.env`에 다
있어 추가 비용 없이 둘을 나란히 돌릴 수 있다.

## 용도별 모델

### 1. 레퍼런스 비전 분석 (지각 층)

레퍼런스 영상의 톤, 자막, 후크 같은 비정형 속성을 설명한다. 결정론 수치(컷, 오디오,
팔레트)는 로컬 라이브러리가 내고, 모델은 그 위에 지각적 묘사만 더한다.

- **1차**: Gemini Flash 계열(모델 ID는 `.env`). 빠르고 싸며 멀티모달. 호출 백엔드는
  `GENAI_BACKEND`가 고른다. 기본은 Vertex 자격이 있으면 Vertex(GCP 크레딧), 없으면
  `GEMINI_API_KEY` lane이다.
- **폴백**: Gemini Pro 계열. 묘사가 얕을 때 한 단계 올린다.
- **홀딩**: Claude 비전. 품질은 좋으나 단일 키 약속을 깨고, 분석 층은 지각 묘사 깊이보다
  결정론 수치가 더 중요해 굳이 키를 늘릴 이유가 약하다.

### 2. 기획·카피 생성 LLM (컨셉, 훅, 스토리보드, 대사, 톤)

가벼운 입력을 구조화된 컨셉으로 펼치고, 3초 후크를 비결정적으로(temperature) 생성한다.
스토리보드와 콘티, 대사 스크립트, 영상 톤 같은 기획과 카피 생성도 이 LLM이 맡는다.

이 용도는 **Gemini 3.1 Pro와 Claude Opus를 한 쌍으로 비교해서 쓴다.** 두 키가 이미 `.env`에
다 있어(`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`), 같은 작업을 둘에 돌려 카피와 기획의 품질을
나란히 본다. 비전 분석이나 이미지처럼 단일 키로 묶을 이유가 없는 텍스트 레인이라, 둘을
일급으로 둔다.

- **비교 쌍(둘 병행)**:
  - Gemini 3.1 Pro (`GEMINI_API_KEY`, `GEMINI_TEXT_MODEL=gemini-3.1-pro-preview`).
  - Claude Opus (`ANTHROPIC_API_KEY`, `CLAUDE_MODEL=claude-opus-4-8`).
  - 컨셉, 훅, 스토리보드/콘티, 대사 스크립트, 영상 톤, 카피 생성에 둘 다 붙여 비교한다.
- **잠정 1차**: `TEXT_MODEL_PRIORITY`의 첫 모델. 기본은 Gemini 3.1 Pro로 두되, 카피와
  내러티브 품질에서 Opus가 나은 작업은 우선순위를 바꿔 Claude를 먼저 호출한다. 작업별로
  더 나은 쪽을 채택하는 식으로 굳혀 간다.
- **홀딩**: 게이트웨이 멀티 라우팅(여러 LLM 자동 분배). 지금 규모엔 과하다. 두 모델을
  명시 우선순위로 비교하는 편이 단순하다.

### 3. 이미지 생성 (에셋 시트와 패널 스틸)

캐릭터와 제품의 멀티뷰 시트, 패널별 스틸을 만든다. 스틸 품질이 영상 품질로 전파되므로
품질을 우선한다. **production에서 컷별 start image도 이 모델로 반복 생성한다**(4번 참고).
컷별 start image에 캐릭터 얼굴·제품이 제대로 들어가야 그 컷에서 일관성이 보존되므로,
영상 백엔드가 Veo든 Kling이든 컷마다 start image를 따로 만들어 주입한다.

- **단일 경로**: Google Nano Banana 계열 (`GEMINI_IMAGE_MODEL`, 기본 `gemini-3.1-flash-image`).
  Gemini 네이티브 이미지 라인의 별칭이라 단일 키(`GEMINI_API_KEY`) 약속 안에서 돈다. 한
  이미지 안에 여러 뷰를 렌더링해 에셋 시트에 잘 맞는다. 더 상위 룩이 필요하면 같은 계열의
  Pro급으로 올린다.
- **제외**: FLUX.2 등 외부 이미지 백엔드. 이미지는 Nano Banana 단일 경로로 좁힌다. 별도
  이미지 provider나 폴백을 두지 않는다.
- **홀딩**: 더 상위 Nano Banana 계열(Pro급). 품질 여력이 필요해지면 올린다. 지금은 기본 계열로 충분.

#### 히어로 스틸 생성 팁 (인물·제품 카탈로그·컷 start image)

인물, 캐릭터 설정 샷, 제품 카탈로그, 컷 start image(영상 생성 reference로 주입)처럼 품질이
결과로 전파되는 스틸은 **히어로 스틸**로 따로 다룬다. 특히 인물 표현이 들어간 이미지에서
이 방법이 확실히 좋다.

- **모델 승격**: 히어로 스틸은 Nano Banana **Pro**로 올린다(`GEMINI_IMAGE_MODEL_HERO`,
  기본 `gemini-3.1-pro-image-preview`). 키·백엔드가 Pro/4K를 못 받으면 기본
  `GEMINI_IMAGE_MODEL`로 폴백한다. 단일 키(`GEMINI_API_KEY`) 약속은 그대로 지킨다.
- **처음부터 1080x1920으로 뽑지 않는다.** 9:16 + `image_size="4K"`로 **고해상도로 생성**한다.
  4K 생성물이 얼굴·피부·제품 디테일을 더 잘 담고, 이후 어떤 크기로 쓰든 여유가 남는다.
- **기본은 4K 원본 그대로 저장한다.** 인물·제품 카탈로그·컷 start image처럼 asset/reference로
  쓰는 스틸은 4K로만 만들면 충분하고, 굳이 리사이즈/크롭하지 않는다(native 4K 유지).
- **최종 1080x1920 배포 프레임이 꼭 필요할 때만** 마감 레시피를 쓴다. 이때는 4K 생성물을
  1080x1920으로 리사이즈/센터크롭한 뒤 JPEG quality=97로 저장하고, 선명도 1.16, 대비 1.04를
  살짝 올린다. 코드에선 `image_client.fit_delivery_frame(...)`가 이 마감을 담당한다.
- **코드 분기**: `ImageClient.generate(..., hero=True)`로 위 경로를 탄다. 캐릭터 설정 샷/제품
  카탈로그(`asset_bible`), 패널 스틸(`stills`), 컷별 start image(`storyboard`) 생성이 모두
  `hero=True`로 호출한다. 일반(비히어로) 스틸은 기존 기본 모델 경로를 그대로 쓴다.

### 4. image-to-video (패널 클립)

패널 스틸을 짧은 클립으로 만든다. 파이프라인에서 가장 비싼 단계라 스토리보드 게이트
뒤에 둔다.

#### 현재 운영 정책 (못박음)

- **기본 모델은 Veo 3.1 Fast로 고정한다.** 기본 호출 모델 ID는
  `veo-3.1-fast-generate-001`이다. Fast가 2026-07-01 maskpack start/end control smoke
  test에서 가장 무난했다. 빠르고, start image를 잘 따랐고, `시원하다` 같은 짧은 네이티브
  발화도 잘 붙었다.
- **Veo 3.1은 Fast와 Standard/Pro만 쓴다.** Standard/Pro 호출 모델 ID는
  `veo-3.1-generate-001`이다. 중요한 히어로 컷, 더 안정적인 질감·얼굴·카메라 품질이
  필요할 때만 Fast에서 승격한다.
- **Veo 3.1 Lite는 기본 경로에서 내린다.** `veo-3.1-lite-generate-001`은 제품 데모 단일
  start image에는 쓸 수 있었지만, start/end control board 테스트에서 split-screen artifact를
  재현했고 전반적으로 기대보다 실망스러웠다. 비용 절감용 실험 외에는 쓰지 않는다.
- **Veo 3.1은 항상 Vertex AI lane으로 호출한다.** Gemini API Veo lane은 쓰지 않는다.
  출력은 GCS로 떨어지고 다운로드 단계가 붙는다. (`GOOGLE_CLOUD_PROJECT`,
  `GOOGLE_APPLICATION_CREDENTIALS`, `VEO_OUTPUT_GCS_URI` 필요.)
- **성능상 최선 후보는 Kling O3다.** 2026-06-30~2026-07-01 smoke test 기준, 이 프로젝트의
  캐릭터 reference 기반 뷰티 제품 영상에서 가장 강한 선택은 `Kling O3`, 특히
  `fal-ai/kling-video/o3/pro/reference-to-video`다. 여러 reference를 한 번에 넣어도 잘 따른다:
  start/action image, 구체적인 캐릭터 설정 이미지, 구체적인 제품 이미지, 멀티샷 storyboard를
  prompt와 함께 넣으면 캐릭터·제품·액션 일관성이 가장 좋았다. 다만 지금 개발 검증 사이클은
  Vertex Veo 경로로 마무리하고, 사용자가 "Kling으로 가자"고 명시하면 그때 기본 영상 모델을
  Kling O3로 바꾼다.
- **Kling O3 reference-to-video가 품질 최우선 경로다.** 한 컷씩 잘라 생성하면 가장 고품질이다.
  멀티샷이 필요할 때도 O3 `multi_prompt`와 storyboard reference를 함께 써서 한 번에 생성할 수
  있으므로 가끔 쓰기 좋다. 품질 욕심이 있거나, 캐릭터·제품·컷 톤을 일관성 있게 밀어붙여야
  하거나, 컷별 일관성이 중요한 복잡한 영상이면 O3 Pro reference-to-video를 우선 검토한다.
- **Kling O3 image-to-video도 충분히 좋다.** 이 경로는 `image_url`로 시작 이미지를 넣고,
  `end_image_url`로 끝 이미지를 넣을 수 있어 Veo 3.1 image-to-video와 치환하기 쉽다. Veo는
  기본적으로 첫 이미지를 중심으로 움직이는 흐름이라, start/end key image를 만들어 넣는 O3
  image-to-video는 명확한 A→B 액션 컷에서 특히 강하다.
- **start image는 필수 입력으로 본다.** 텍스트 프롬프트만으로는 제품, 캐릭터, 액션, 끝
  상태를 안정적으로 고정하기 어렵다. 먼저 Nano Banana로 컷별 key image를 만든 뒤 그 이미지를
  Veo image-to-video에 넣는다.
- **start image가 끝 상태를 충분히 표현하지 못할 때는 프롬프트로 보완한다.** 한 장의 start
  image는 이후 동작과 end frame을 직접 담기 어렵다. 중요한 컷은 Nano Banana로 한 장 안에
  start/end keyframe board를 만들고, 프롬프트에 "왼쪽은 시작, 오른쪽은 끝 상태이며 최종
  영상은 split-screen이 아니라 하나의 연속 full-screen shot"이라고 명시한다. 2026-07-01
  테스트에서 Fast와 Standard/Pro는 이 방식을 잘 따랐고, Lite는 split artifact가 생겼다.
- **on-camera voice는 영상 모델 네이티브 발화로 처리한다.** voice 파일을 따로 넣지 않아도
  `generate_audio=True`와 대사 스크립트가 포함된 프롬프트로 캐릭터 발화와 오디오를 함께
  생성한다. 2026-06-30 smoke test에서 image+text 프롬프트만으로 생성한 발화는 어느 모델이든
  어느 정도 자연스러웠다. 반대로 외부 audio/voice 파일을 영상 모델에 넣어 립싱크시키는
  경로는 Seedance 2.0, Veo 3.1, Kling O3 모두 기본 채택할 품질이 아니었다. 별도 voice
  파일은 화면 밖 나레이션/보이스오버에만 의미 있게 쓰고, 화면 안 인물이 말해야 하면 영상
  모델에 대사와 목소리까지 직접 생성하게 한다.
- **fal.ai는 영상 Kling O3 후보용으로만 둔다(이미지에는 쓰지 않는다).** `FAL_KEY`를 `.env`에
  넣고 결제를 열어 뒀지만(2026-06-30), 영상 생성의 현재 개발 기본 경로는 Veo 3.1 Fast +
  Standard/Pro다. Kling O3는 성능상 최선 후보이되, 기본 모델 전환은 사용자가 명시적으로 지시할
  때 한다. Seedance 영상은 사용자가 별도 비교를 공식 요청할 때만 켠다. Veo는 절대 fal로 호출하지
  않는다(Vertex 전용). 이미지는 Nano Banana 단일 경로다(3번 참고).
- **Seedance 2.0은 지금 워크플로우의 기본 후보에서 사실상 내린다.** 2026-06-30
  storyboard/persona/product reference smoke test에서 `bytedance/seedance-2.0/fast/reference-to-video`
  는 얼굴·인물 reference를 likeness/private information 가능성으로 provider validation 단계에서
  차단했다. 이 프로젝트는 캐릭터 외모와 제품 reference를 함께 넣는 흐름이 핵심이라,
  Seedance의 reference 검열은 단순 품질 문제가 아니라 사용성 리스크다.
- **저비용 폴백**: 영상 모델을 끄면 스틸을 켄 번스 모션으로 같은 조립 경로에 태운다.
  모델 예산 없이도 끝까지 돈다. 워킹 스켈레톤의 기본 경로다.

#### Veo 3.1 계열 입력/오디오/샷 지원

기준은 Vertex AI `generate_videos` lane이다. 이 표는 모델 선택과 어댑터 구현의 계약으로
쓴다.

| 항목 | Veo 3.1 Fast `veo-3.1-fast-generate-001` | Veo 3.1 Standard/Pro `veo-3.1-generate-001` | 운영 결정 |
|---|---|---|---|
| 상태 | GA/운영 기본 | GA/고품질 승격 | 기본은 Fast, 중요한 히어로 컷만 Standard/Pro 승격 |
| 입력 | Text, Image | Text, Image, Audio | 기본 요청은 text + optional image만 사용 |
| Video input | 미지원 | 미지원 | 생성 원본으로 기존 video를 직접 넣지 않는다 |
| Audio input | 미지원 | 문서상 지원 | 실측상 립싱크용으로는 기본 경로에서 쓰지 않는다. 별도 audio는 voiceover 전용 |
| 출력 | Video with native audio | Video with native audio | `generate_audio=True`를 켜고 Veo가 영상+음성을 함께 만들게 한다 |
| 대사/voice | 프롬프트 안 대사 스크립트로 on-camera 발화 생성 | 프롬프트 안 대사 스크립트로 on-camera 발화 생성 | 별도 TTS보다 이 경로를 우선한다 |
| 립싱크 | 전용 립싱크 API는 아니지만 네이티브 발화가 얼굴 움직임과 함께 생성됨 | 전용 립싱크 API는 아니지만 네이티브 발화가 얼굴 움직임과 함께 생성됨 | 캐릭터가 화면에 말하는 장면은 Veo에 한 번에 맡긴다 |
| Image-to-video | 지원 | 지원 | 패널 스틸을 첫 프레임/시각 reference로 넣는다 |
| First/last frame | 지원 | 지원 | 시작/끝 구도가 중요한 샷에서 사용 |
| Reference asset images | 미지원 | 지원(Preview) | 캐릭터/제품 일관성이 더 중요하면 Standard/Pro 승격 |
| Reference style images | 미지원 | 미지원 | 스타일은 별도 이미지 reference가 아니라 프롬프트/분석 profile로 전달 |
| Extend videos | 지원(Preview) | 지원(Preview) | 멀티샷 기본 수단은 아님. 필요 시 이전 Veo 클립 연장에만 사용 |
| 단일 요청 output 수 | 최대 4개 | 최대 4개 | 비용 때문에 기본 `number_of_videos=1` |
| duration | 4, 6, 8초 | 4, 6, 8초. reference image-to-video는 8초 제약 | 패널 기본은 4초. reference asset 사용 시 8초 제약을 고려 |
| 해상도/비율 | 720p/1080p, 9:16/16:9 | 720p/1080p, 9:16/16:9 | 기본은 9:16 720p, 최종 품질 필요 시 1080p |
| 멀티샷 | 하나의 shot list를 구조적으로 받는 API는 아님 | 하나의 shot list를 구조적으로 받는 API는 아님 | 스토리보드 패널별로 여러 번 생성하고 조립한다 |

결론: **립싱크가 필요하면 영상 모델에 대사 스크립트와 목소리 지시를 직접 넣는다.** 영상
모델이 캐릭터, 입 움직임, 음성을 함께 샘플링해야 그나마 자연스럽다. 별도 TTS/voice 파일을
영상에 주입하는 방식은 Seedance 2.0 reference audio, Veo 3.1 audio input, Kling O3
`voice_id` binding 모두 smoke test에서 기대보다 약했다. `voiceover`는 화면 밖 내레이션에만
쓰고, on-camera 립싱크의 기본 경로로 쓰지 않는다.

#### 모델 비교와 선택 기준

개발 기본값은 Veo 3.1 Fast다. 그러나 품질 기준의 최선 선택은 Kling O3다. 지금은 전체 개발
검증 사이클을 Veo 3.1 Fast로 마친 뒤, 사용자가 Kling 전환을 명시하면 Kling O3를 기본 영상
경로로 올린다. voice의 기본 경로는 나레이션(voiceover)이므로([ADR.md](ADR.md) ADR-0012),
대부분의 컷은 발화 능력과 무관하게 만들고 목소리는 TTS 나레이션으로 얹는다. 화면 인물이
직접 말하는 `on_camera`가 필요한 컷에서만 모델 네이티브 발화를 쓰고, **여러 컷에서 목소리를
일관되게 유지하며 립싱크해야 하면 `Kling O3 Pro reference-to-video`가 유일**하다.

| 모델 | 잘 만드는 유형 | 한계 |
|---|---|---|
| **Veo 3.1 Fast** (기본) | 제품 데모, 뷰티 사용 컷, 마스크팩/젤 도포 같은 짧은 액션, start image 기반 단일 컷, 짧은 on-camera 발화 | start image 없이 텍스트만 넣으면 원하는 제품/끝 상태를 놓치기 쉽다. start/end board를 쓸 때는 split-screen 금지를 강하게 써야 한다 |
| **Veo 3.1 Standard/Pro** (고품질 승격) | Fast보다 중요한 히어로 컷, 더 안정적인 얼굴·질감·카메라 품질, start/end control이 중요한 최종 후보 | Fast보다 느리고 비싸다. 외부 voice 파일 주입은 기본 제외 |
| **Veo 3.1 Lite** (제외/비권장) | 단순 단일 start image 제품 데모를 저비용으로 확인하는 실험 | start/end control board에서 split-screen artifact를 만들었고 품질이 기대보다 낮았다. 기본 경로에서 제외 |
| **Kling O3 Pro reference-to-video** (성능 최선) | 복잡한 뷰티 제품 영상, 자연스럽게 말하는 사람 클로즈업, 캐릭터·제품·스토리보드 reference를 모두 넣는 컷, 멀티샷 storyboard를 한 번에 넣는 고품질 생성 | 비용이 높다. 지금 개발 기본값은 아니며, 사용자가 전환을 지시하면 기본 후보로 올린다 |
| **Kling O3 Standard reference-to-video** (비용 절충) | O3 Pro와 같은 reference-to-video 흐름을 더 낮은 비용으로 확인, 컷별 생성 후 조립하는 후보 | Pro보다 디테일과 음성 안정성이 낮을 수 있다 |
| **Kling O3 Standard/Pro image-to-video** (Veo 치환 쉬움) | start image + end image가 있는 명확한 A→B 액션 컷, Veo image-to-video와 비슷한 인터페이스로 교체해야 하는 경우 | 복잡한 캐릭터/제품/스토리보드 reference를 한 번에 묶는 데는 reference-to-video가 더 적합 |
| **Seedance 2.0 Fast** (주의) | 기존 촬영본 확장, 영화적인 연출 비교 | face/persona reference 검열과 audio drift 때문에 캐릭터 reference 기반 제품 광고 워크플로우에서는 기본 사용이 어렵다 |

선택 가이드: 개발 기본은 Vertex API의 `Veo 3.1 Fast`다. 품질이 부족한 최종 히어로 컷은
`veo-3.1-generate-001`로 승격한다. 정말 품질 욕심이 있거나, 캐릭터·제품·컷 톤을 일관성 있게
밀어붙여야 하거나, 복잡한 멀티샷 storyboard를 reference와 함께 제어해야 하면 Kling O3를 쓴다.
그중 최선은 `fal-ai/kling-video/o3/pro/reference-to-video`다. 컷별로 잘라 생성한 뒤 합치는
경로가 가장 고품질이고, 멀티샷을 한 번에 생성해야 할 때도 O3 reference-to-video가 가능하다.
단순 A→B 액션 컷은 O3 image-to-video에 `image_url`과 `end_image_url`을 넣는 방식이 Veo와
치환하기 쉽다.

컷 구조에 따른 결론:

- **원컷으로 밀어붙이면** Veo 3.1 Pro로도 충분히 커버된다(그래도 품질은 Kling이 낫다).
  숏폼은 컷이 너무 많으면 피곤하니, 한두 컷으로 가는 것도 유효한 선택이다.
- **여러 컷으로 나뉘면** 멀티샷이든 컷별 생성이든 Kling O3가 Veo보다 낫다. 컷별 생성은
  만들고 붙이는 수고가 있지만 퀄리티가 더 좋다. **컷별 생성 시 start image에 캐릭터 얼굴이
  제대로 나와야 그 컷에서 얼굴이 보존된다.** Kling O3 reference-to-video는 캐릭터 설정 샷과
  제품 이미지를 reference로 함께 넣을 수 있어 얼굴·제품 일관성 확보가 더 쉽다.
- **편집 팁**: 컷을 조금 길게(약 1초 여유) 만든 뒤 불필요한 앞뒤를 잘라 붙이면 퀄리티가
  올라간다. 단 컷이 많아지면 1초마다 비용이 쌓이니 여유 길이는 아껴 쓴다.
- BGM을 잘 깔고 리듬감 있게 컷을 나눠 생성·편집·합성하는 것이 최선이다.

개발 순서와 에셋 주입:

- **개발은 Veo 3.1 Fast로 먼저 끝내고, 이후 Kling으로 갈아탄다.** Kling으로 전환할 때
  비로소 미리 만들어 둔 캐릭터·제품 카탈로그 이미지(3번 Nano Banana 산출)를 영상 생성
  모델에 reference로 그대로 주입할 수 있어 일관성에 유리하다(Kling O3 reference-to-video).
- **컷별 start image는 Veo든 Kling이든 각 컷마다 따로 생성해 주입해야** 시작 프레임이
  일관된다. 이 컷별 start image는 계속 Nano Banana(3번)로 만든다. 즉 Nano Banana는 에셋
  시트뿐 아니라 production의 컷별 start image 생성에도 반복해서 쓰인다.

- **제외**: 구버전 영상 모델(Veo 3 등). 2026-06-30자로 셧다운돼 신규 연동은 최신 세대로.

#### 컷 길이 한계와 멀티샷 기본 (중요)

생성 클립 길이 한계가 컷 전략을 정한다.

- **모델별 생성 길이**: Kling은 한 번에 **3~15초**, Veo 3.1은 **4~8초**를 만든다. 그래서
  **3초보다 짧은 컷은 단독 생성이 불가능**하고 멀티샷으로 뽑아야 한다.
- **이 프로젝트의 숏폼은 보통 1~2초 단위 컷이 기본**이다. 따라서 **멀티샷 생성이 기본
  전략**이다. 멀티샷은 한 번에 여러 컷을 일관되게 붙여서 내주므로 생성이 쉽고 컷 사이
  일관성도 좋다. 멀티샷 기능을 최대한 활용한다.
- **10초 이상은 한 번에 어렵다**(모델별 상한). 더 길면 여러 번 생성해 이어 붙이되,
  **이전 생성 영상의 마지막 프레임을 캡처해 다음 생성의 start image로 재사용**해 일관성을
  잇는다.
- **execute 적용**: 스토리보드 콘티를 짠 뒤, 초 단위(1~2초) 컷이 필요하면 **멀티샷을 기본**
  으로 가져간다. 컷 단위 타이밍을 BGM bpm과 맞춰 요청한다(아래 5번).

### 5. 배경 음악 (BGM)

주 경로는 자막에 뮤직 베드다. **BGM 선정과 컷-음악 동기는 매우 중요하다.** 음악 bpm과
컷 변화 주기가 맞아야 영상이 리듬감 있게 붙는다.

- **bpm ↔ 컷 정렬(필수)**: 스토리보드의 평균 컷 길이로 목표 bpm을 잡아 BGM 생성 요청에
  넣는다. 컷이 비트 위에 떨어지도록(또는 의미·액션 컷이면 비트와 어긋나지 않도록) 맞춘다.
  예: 평균 컷 1.0초면 비트 간격 1.0초 = 60bpm 계열의 배수(120bpm에서 2박마다 컷)로 잡는다.
  대략 `bpm ≈ 60 / 평균_컷_초 * k`(k는 컷당 비트 수). 이 정렬은 **별도 체크로 검증**한다
  (생성물 BGM bpm 추정 vs 컷 주기). 안 맞으면 BGM 재생성 또는 컷 타이밍 보정.
- **1차**: Lyria 3 음악 생성 (`LYRIA_MODEL`). MusicSpec(mood/style/tempo)과 컷 정렬 bpm으로 요청.
  - **길이 상한**: Lyria 3(Clip)은 **한 번에 30초까지** 생성한다. 대부분의 숏폼은 30초 이하라
    Clip으로 충분하다.
  - **30초 초과**: 30초를 넘는 트랙이 필요하면 **Lyria 3 Pro**로 올린다. 기본값은 Clip이고,
    스토리보드 총길이가 30초를 넘을 때만 Pro로 전환한다.
- **폴백**: 사용자가 제공한 음악 파일, 또는 무음. 외부 스톡 검색 provider는 기본 경로에서
  제외한다.
- **홀딩**: 없음. 생성과 제공 파일 두 경로면 충분.

### 6. voice (나레이션·발화)

**voice는 되도록 사용하되, 기본 전달은 나레이션(`voiceover`)이다**([ADR.md](ADR.md)
ADR-0012). 실측 결과 나레이션 구조가 구현상 가장 자연스럽고 쉬웠다. 화면 인물이 직접
말하는 on-camera 립싱크는 욕심내지 않고, 역동적으로 사람이 나와 말해야 하는 컷에서만 켠다.

전달은 셋이다. `voiceover`(화면과 분리된 TTS 나레이션), `on_camera`(영상 모델이 네이티브로
등장인물을 말하게 함), `none`(음악 베드만).

- **1차(voiceover, 나레이션) = ElevenLabs로 못박는다.** 한국어든 영어든 기본은 ElevenLabs
  (`ELEVENLABS_API_KEY`)다. 실측상 ElevenLabs가 Google TTS보다 한 수 위라, 언어와 무관하게
  ElevenLabs를 먼저 호출한다. 캐릭터 개성을 살린 목소리를 길게 연속으로 뽑을 수 있어 컷이
  나뉘어도 목소리 톤이 일관된다. 음색은 캐릭터 설정(`ModelSpec`)에서 유도한다.
  - **ElevenLabs 모델은 `eleven_v3`를 기본으로 한다**(`ELEVENLABS_TTS_MODEL=eleven_v3`).
    다국어 표현력이 가장 좋아 한국어·영어 나레이션 기본값으로 둔다.
  - **한국어는 voice 선택이 품질을 좌우한다.** `eleven_v3`가 다국어라도 프리메이드 voice마다
    한국어 발음·억양 품질이 다르다. 한국어에 적당한 여성 프리메이드 voice **Bella**를 기본으로
    쓴다(코드가 계정에서 이름으로 조회. Bella의 ID는 계정·라이브러리 버전마다 달라 하드코딩
    하지 않는다). 다른 voice를 원하면 `ELEVENLABS_VOICE_ID`로 고정하고, 캐릭터 설정에 맞게
    안정성·스타일 파라미터로 변형한다. 무료 플랜에서 라이브러리 voice가 막히면 계정 접근
    가능한 여성 voice로 자동 폴백한다.
  - **Voice Design v3는 홀딩.** 캐릭터 전용 커스텀 voice 설계는 매력적이지만 지금은 검토만
    하고 안 쓴다. 프리메이드 voice + 파라미터 변형으로 충분하다.
- **폴백(voiceover) = Google TTS.** ElevenLabs 키가 없거나 막힐 때만 쓴다. Google TTS를
  쓴다면 **최신 Gemini 3.1 TTS preview**(`gemini-3.1-flash-tts-preview`)가 가장 낫다. 예전
  Chirp 3 계열이 아니라 이 3.1 preview를 기준으로 한다.
- **2차(on_camera, 네이티브 발화)**: 역동적으로 화면 인물이 직접 말해야 할 때만. 별도 voice를
  만들지 않고 프롬프트에 캐릭터 설정과 대사 스크립트를 넣어 영상·음성·입 움직임을 한 번에
  생성한다. **원컷이면 Veo/Kling 둘 다 가능**하지만, **여러 컷에서 목소리 톤을 일관되게
  유지하며 립싱크해야 하면 `Kling O3 Pro reference-to-video`가 유일한 선택**이다(컷이 나뉘면
  다른 경로는 컷마다 목소리가 달라진다).
- **절대 금지**: voice를 먼저 생성해 영상 모델에 주입하고 립싱크를 맞추는 방식. 실측에서
  무리였다. 시도하지 않는다.
- **제외**: 전용 토킹헤드/립싱크 아바타 파이프라인(HeyGen 등).

요지: 사람 목소리가 필요하면 **나레이션(ElevenLabs `eleven_v3`가 기본, 없을 때만 Google
TTS 3.1 preview)을** 기본으로 가고, 화면 인물이 직접 말하는 연출이 꼭 필요할 때만 영상 모델
네이티브 발화로, 그것도 멀티컷 일관성이 필요하면 Kling O3 Pro로 간다.

### 7. 자막 타이밍 (비모델)

자막 텍스트와 타이밍은 스토리보드 패널에서 온다. 음성 인식이나 강제 정렬이 필요 없다.

- **1차**: 스토리보드 패널의 `t_start`/`t_end`/`subtitle_text`를 그대로 쓴다. 모델 호출 없음.
- **홀딩**: whisperX 강제 정렬. 보이스오버 타이밍을 음성에서 따와야 하는 경우의 폴백으로만
  남긴다. 주 경로에선 불필요.

## 홀딩과 제외 한눈에

| 대상 | 용도 | 상태 | 이유 |
|---|---|---|---|
| Gemini 3.1 Pro vs Claude Opus | 기획·카피 LLM(컨셉·훅·스토리보드·대사·톤) | 비교 중 | 두 키 다 보유, 일급으로 병행 비교. 작업별로 나은 쪽 채택, 잠정 1차는 Gemini 3.1 Pro |
| Veo 3.1 Fast (Vertex 전용) | i2v | 개발 1차 고정 | 개발 검증 cycle의 영상 생성 기본. start image 필수, 항상 Vertex lane, Gemini API Veo 미사용 |
| Veo 3.1 Standard/Pro (Vertex 전용) | i2v | 고품질 승격 | 중요한 히어로 컷에서 Fast 품질이 부족할 때만 승격 |
| Veo 3.1 Lite (Vertex 전용) | i2v | 제외/비권장 | start/end control board에서 split artifact 발생, 품질이 실망스러워 기본 경로 제외 |
| Kling O3 Pro reference-to-video (fal.ai) | i2v | 성능 최선/전환 대기 | 현시점 이 프로젝트에서 품질상 최선. 여러 reference와 storyboard를 한 번에 넣기 좋음. 개발 cycle 완료 후 사용자가 전환 지시하면 기본 후보로 올림 |
| Kling O3 Standard reference-to-video (fal.ai) | i2v | 비용 절충 후보 | Pro보다 저렴한 Kling 경로. 컷별 생성/조립 후보로 유용 |
| Kling O3 Standard/Pro image-to-video (fal.ai) | i2v | Veo 치환 후보 | `image_url` + `end_image_url`로 start/end 제어 가능. 명확한 A→B 액션 컷에서 강함 |
| Seedance 2.0 Fast (fal.ai) | i2v | 홀딩/주의 | 영화적 연출과 기존 촬영본 확장은 장점이나, face/persona reference 검열과 audio drift 때문에 캐릭터 reference 기반 제품 광고 워크플로우에서는 기본 사용이 어렵다 |
| Gemini API Veo lane | i2v | 제외 | Veo 3.1은 Vertex 전용으로 못박음, Gemini API Veo는 안 씀 |
| Claude 비전 | 비전 분석 | 홀딩 | 단일 키 약속 위배, 분석 층은 결정론 수치가 우선 |
| 게이트웨이 멀티 라우팅 | LLM | 홀딩 | 현 규모에 과함, 한쪽으로 확정할 거라 불필요 |
| 상위 이미지 모델 일반 | 이미지 | 홀딩 | 1차로 충분, 품질 여력 필요 시 승격 |
| Replicate i2v | i2v | 홀딩 | 키 미보유, 단가 fal과 동일 수준 |
| 구버전 영상 모델 | i2v | 제외 | 셧다운, 최신 세대로 대체 |
| ElevenLabs `eleven_v3` | voice(나레이션) | 1차 고정 | 한국어·영어 공통 기본. Google TTS보다 한 수 위라 언어 무관 먼저 호출. 한국어 기본 voice는 Bella(계정에서 이름 조회), `ELEVENLABS_VOICE_ID`로 교체 |
| Google TTS 3.1 preview (`gemini-3.1-flash-tts-preview`) | voice(나레이션) | 폴백 | ElevenLabs 키가 없거나 막힐 때만. Chirp 3가 아니라 최신 3.1 preview 기준 |
| ElevenLabs Voice Design v3 | voice(나레이션) | 홀딩 | 캐릭터 전용 커스텀 voice 설계. 프리메이드 voice + 파라미터 변형으로 충분해 지금은 검토만 |
| HeyGen 전용 아바타 | 음성/영상 | 제외 | 전용 립싱크 파이프라인 미구현. 영상 모델 네이티브 발화(on_camera)로 대체 |
| whisperX | 자막 정렬 | 홀딩 | 자막은 스토리보드에서 옴, 보이스오버 폴백만 |

## 갱신 규칙

- 모델을 바꾸면 이 문서의 해당 용도부터 고치고 `.env`에 반영한다.
- 홀딩을 채택하거나 1차를 내릴 때는 표의 상태와 이유를 갱신한다. 적용해 본 뒤 안 쓰기로
  했다면 그 결과를 이유에 남긴다.
- 모델 자체의 비교 회고(무엇을 써 보고 어땠는지)는 회고 문서로 따로 정리한다. 이 문서는
  현재 선택과 그 근거만 짧게 유지한다.
