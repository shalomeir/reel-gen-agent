# 최종 리포트 — 15-lightweight-linen-open-collar-20260702-071800

## 유저 입력
- 목적: 영상 목적: 미국인 남성 틱톡커가 여름 휴가 스타일링 팁을 재치 있게 직접 말하며 소개하고, 마지막에 가벼운 리넨 오픈카라 셔츠를 자연스럽게 추천하는 15초 세로 숏폼
제품: Lightweight Linen Open-Collar Summer Shirt / 여름 휴가와 리조트 룩에 가볍게 걸치는 남성용 리넨 오픈카라 셔츠 / men's summer shirt
캐릭터: late-30s / male / witty, charismatic American male creator talking to camera
스타일: hyper_realistic
언어: en
발화: on_camera
- 제품: Lightweight Linen Open-Collar Summer Shirt
- 레퍼런스: -

## 캐릭터
- age: late-30s
- gender: male
- look: exceptionally attractive American man, highly photogenic celebrity-tier face, charismatic and witty 'it-guy' vibe, flawless model-tier features, magnetic viral TikToker appearance

## 스타일
- tone: breezy, charismatic, sun-drenched, sophisticated
- pacing: slow_demo
- motion: gentle
- palette: crisp white, ocean blue, sunlit gold, warm beige

## 훅
- type: H6
- headline: Want the yacht-owner look?
- bottom_caption: The ultimate summer style hack
- visual: The creator leans casually against a sun-drenched balcony railing, effortlessly adjusting the open collar of his breezy linen shirt while flashing a magnetic, knowing smirk directly at the lens.

## 스토리보드
- `00:00` [establish] — The creator leans casually against a sun-drenched balcony railing, the ocean sparkling behind him. He effortlessly adjusts the open collar of his breezy linen shirt, flashing a magnetic, knowing smirk directly at the lens. 자막:"Want the yacht-owner look?"
- `00:03` [demonstrate] — The warm ocean breeze gently ripples the lightweight fabric. His hand slowly grazes the textured linen weave near the open collar, highlighting the breathable, unrestrictive drape of the shirt against his skin. 자막:"Ditch the stiff cotton. Pure breathable linen."
- `00:07` [transformation] — He steps back from the railing, unhurriedly rolling up one sleeve to forearm length. The open collar perfectly frames his relaxed posture as he turns his head to deliver a witty, charismatic grin. 자막:"Effortless, even at 90 degrees."
- `00:10` [payoff/cta] — He smoothly slides on a pair of sleek sunglasses, playfully tapping the crisp linen chest of his shirt with two fingers. He gives a confident nod and points subtly toward the bottom edge of the screen. 자막:"Grab your summer staple below."

## 최종 의견
(미작성)

## 노드 흐름
production_plan -> stills -> visuals -> voice -> bgm -> sfx -> assemble -> verify -> describe -> evaluate

## 사용 모델
video=fal-ai/kling-video/o3/pro/image-to-video, image_still=gemini-3.1-pro-image-preview, image_asset=gemini-3.1-pro-image-preview, bgm=lyria-3-pro-preview, llm=gemini-3.1-pro-preview

## 예상 비용 (단가 기준일 2026-07-01, USD, 실제 청구와 다를 수 있음)

| 항목 | 모델 | 단위 | 사용량 | 단가 | 소계 |
|---|---|---|---|---|---|
| 패널 스틸 (세그먼트당 1장(히어로 4K)) | gemini-3.1-pro-image-preview | 장 | 2 | $0.240 | $0.480 |
| 에셋 이미지 (캐릭터·제품·패키지·키비주얼(히어로 4K)) | gemini-3.1-pro-image-preview | 장 | 2 | $0.240 | $0.480 |
| 영상 클립 (4개 클립, 오디오 포함) | fal-ai/kling-video/o3/pro/image-to-video | 초 | 14 | $0.140 | $1.960 |
| BGM | lyria-3-pro-preview | 클립 | 1 | $0.040 | $0.040 |
| 품질 평가 (conformance + rubric) | gemini-2.5-flash | 호출 | 2 | $0.020 | $0.040 |
| 기획 LLM (추정: 약 10회 호출(입력~20k/출력~8k 토큰)) | gemini-3.1-pro-preview | 회차 | 1 | $0.136 | $0.136 |
| **합계** |  |  |  |  | **$3.136** |

- 단가는 공개 근사치(기준일 2026-07-01)이며 실제 청구와 다를 수 있음
- ken_burns/합성 BGM 등 로컬 폴백은 $0으로 계산
- 기획 LLM은 회차 휴리스틱 추정치(실제 토큰 사용량 관측 아님)
- 이미지는 히어로 4K 요율. 스틸(세그먼트/컷당 1장)과 에셋(캐릭터·제품·패키지·키비주얼) 모두 집계
- SFX는 플랜이 켰을 때만 집계(컷 sfx 큐 기준). Kling O3는 배선되면 자동 반영
- 재계획·재생성(run --max-iters) 반복 시 스틸/영상 비용은 회차당으로 곱해짐(1회 기준 추정)
- 미등록 모델(단가 미반영, $0 처리): gemini-3.1-pro-preview

## BGM
- 방식 gen, 모델 lyria-3-pro-preview
- 음악: 무드 charismatic, breezy, sophisticated, effortless, 장르 sun-drenched balearic organic house with a steady, laid-back four-on-the-floor groove, 악기 warm rolling bass, crisp muted funk guitar plucks, breezy atmospheric synth pads, gentle organic percussion like shakers and congas, soft minimal kick drum, 존재감 prominent

## 평가
- conformance: {'checks': [{'code': 'media.file_valid', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '파일 유효, ffprobe 파싱됨'}, {'code': 'media.container_complete', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '컨테이너 길이 정보 존재(잘림 없음)'}, {'code': 'media.video_decodable', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': '16 frames', 'detail': '프레임 디코드됨'}, {'code': 'media.audio_present', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '오디오 스트림 존재'}, {'code': 'media.aspect_ratio', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': '9:16', 'actual': '9:16', 'detail': None}, {'code': 'media.duration_positive', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': '13.771', 'detail': None}, {'code': 'media.resolution_min', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': '>= 480px wide', 'actual': '1080x1920', 'detail': None}, {'code': 'media.not_black', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'black ratio 0.00', 'detail': '정상 밝기 프레임 존재'}, {'code': 'media.not_frozen', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'adjacent diff 38.98', 'detail': '프레임 변화 있음'}, {'code': 'media.audio_not_silent', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'peak -1.72 dBFS', 'detail': '오디오 신호 존재'}, {'code': 'perceptual.volume_loudness', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': '-21.0 ~ -9.0 LUFS', 'actual': '-20.41 LUFS', 'detail': None}, {'code': 'perceptual.volume_no_clipping', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': '<= 0.0 dBTP', 'actual': '-1.72 dBFS', 'detail': None}, {'code': 'perceptual.cut_no_broken_frames', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '깨진 프레임 없음'}, {'code': 'perceptual.cut_transition_clean', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '영상에 감지된 결함이 없습니다.'}, {'code': 'perceptual.subtitle_in_safe_zone', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.subtitle_not_awkward', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.subtitle_legible', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.product_fit_purpose', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '제품이 목적에 맞게 표현됨'}, {'code': 'perceptual.model_appeal_fit', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '등장인물이 목적 전달에 적절'}, {'code': 'perceptual.subtitle_text_match', 'category': 'perceptual', 'intrinsic': False, 'status': 'skip', 'expected': None, 'actual': None, 'detail': '기대 자막 없음(레퍼런스/무자막)'}, {'code': 'perceptual.transition_as_specified', 'category': 'perceptual', 'intrinsic': False, 'status': 'skip', 'expected': None, 'actual': None, 'detail': '스토리보드 전환 타입 필드 추후'}], 'passed': True, 'counts': {'pass': 19, 'fail': 0, 'skip': 2}, 'source': {'path': 'outputs/15-lightweight-linen-open-collar-20260702-071800/final.mp4', 'url': None, 'extractor_id': None}}
- rubric: {'dimensions': [{'code': 'D1', 'key': 'hook_strength', 'name': 'Hook 강도(첫 1~3초)', 'weight': 0.2, 'role': 'gate', 'score': 4, 'normalized': 0.75, 'rationale': "잘생긴 남성이 매력적인 배경에서 '요트 오너 룩'을 언급하며 시청자의 호기심과 동경심을 자극합니다."}, {'code': 'D2', 'key': 'watch_completion', 'name': '시청 완결 설계', 'weight': 0.18, 'role': 'gate', 'score': 4, 'normalized': 0.75, 'rationale': '제품의 장점을 명확하게 보여주고 마지막에 구매를 유도하며 자연스러운 흐름으로 시청을 유도합니다.'}, {'code': 'D3', 'key': 'content_value', 'name': '콘텐츠 가치', 'weight': 0.15, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '제품의 특징(린넨, 통기성, 가벼움)과 여름철 착용의 이점을 명확히 전달하며 구매 욕구를 자극합니다.'}, {'code': 'D4', 'key': 'brand_integration', 'name': '브랜드 통합 자연스러움', 'weight': 0.14, 'role': 'additive', 'score': 5, 'normalized': 1.0, 'rationale': '제품이 영상의 중심이며, 셔츠의 특성과 착용의 이점이 자연스럽게 연결되어 광고처럼 느껴지지 않습니다.'}, {'code': 'D5', 'key': 'call_to_action', 'name': '행동 유발 설계', 'weight': 0.14, 'role': 'additive', 'score': 3, 'normalized': 0.5, 'rationale': "'아래에서 구매하세요'라는 명확한 CTA가 있지만, 공유나 추가적인 상호작용을 유도하는 요소는 부족합니다."}, {'code': 'D6', 'key': 'platform_native', 'name': '플랫폼 네이티브성', 'weight': 0.09, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '짧은 길이, 세로형 포맷, 텍스트 오버레이 등 숏폼 플랫폼의 특징을 잘 활용하여 제작되었습니다.'}, {'code': 'D7', 'key': 'trust_authenticity', 'name': '신뢰·진정성', 'weight': 0.1, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '린넨 셔츠의 특성을 과장 없이 보여주며, 모델의 자연스러운 모습이 제품의 편안함과 신뢰도를 높입니다.'}], 'gate_coefficient': 0.5625, 'additive_core': 0.75, 'gated_score': 42.19, 'flat_score': 75.0, 'gate_passed': True, 'passed': True, 'summary': '린넨 셔츠의 시원함과 스타일리시함을 강조하며 여름철 필수템으로 제안하는 숏폼 광고.', 'expected_effect': "이 영상은 '요트 오너 룩'이라는 키워드로 특정 라이프스타일을 동경하는 시청자, 특히 여름철 시원하고 스타일리시한 의류를 찾는 남성들이 멈춰 보게 할 것입니다. 제품의 소재와 착용감을 시각적으로 잘 보여주어 구매 전환율이 높을 것으로 예상되며, '여름 휴가룩'이나 '남성 린넨 셔츠' 관련 검색 시 노출되어 해당 틈새시장에서 좋은 도달률을 보일 수 있습니다.", 'source': {'path': 'outputs/15-lightweight-linen-open-collar-20260702-071800/final.mp4', 'url': None, 'extractor_id': None}, 'scored': True}

## verify 교정(repair)
- 되돌린 횟수: 0
- 미해결 fail: 없음

## 바이럴 예측
(미작성)

## 노드별 프롬프트
### visuals
[segment 0] A single vertical 9:16 clip that moves through 2 shots played one after another over time (a smoothly edited sequence with longer, gentle holds and soft transitions (each shot lingers, calm and unhurried)).
Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, minimal, graceful subject motion — not busy or energetic, even though cuts are quick.
Keep the SAME product identical in every shot — the product is: Lightweight Linen Open-Collar Summer Shirt, a men's summer shirt, lightweight linen, distinctive: open-collar, lightweight linen fabric. Its shape, packaging and colors must stay exactly the same across all shots.
Keep the same person consistent across every shot; exactly one person, no duplicate people.
The person speaks to the camera in English only, with natural, realistic lip-sync. Every spoken word is in English; never any other language, no gibberish.
Do not render any on-screen text, captions, subtitles, letters, words or watermarks; clean footage with no text overlay.
character: exceptionally attractive American man, highly photogenic celebrity-tier face, charismatic and witty 'it-guy' vibe, flawless model-tier features, magnetic viral TikToker appearance; product (keep identical in every shot): Lightweight Linen Open-Collar Summer Shirt, a men's summer shirt, lightweight linen, distinctive: open-collar, lightweight linen fabric; mood and tone: witty, effortless, breezy, charismatic; framing: vertical 9:16, subject large — upper body only by default; color grading matching this palette: sun-drenched beige, ocean blue, crisp white, warm golden hour; location: A sun-drenched luxury resort balcony overlooking a bright tropical beach; lighting: Bright, natural afternoon sunlight with a warm golden glow and soft, flattering shadows; mood: Breezy, vibrant, and effortlessly stylish summer vacation vibe; no on-screen text, captions, letters or watermarks
Shot 1: Medium shot — the creator, The creator leans casually against a sun-drenched balcony railing, the ocean sparkling behind him. He effortlessly adjusts the open collar of his breezy linen shirt, flashing a magnetic, knowing smirk directly at the lens.. Camera: Slow push-in. The person says in English: "This open-collar linen is my summer staple."
Shot 2: Macro close-up — the Lightweight Linen Open-Collar Summer Shirt product in focus, The warm ocean breeze gently ripples the lightweight fabric. His hand slowly grazes the textured linen weave near the open collar, highlighting the breathable, unrestrictive drape of the shirt against his skin.. Camera: Gentle downward tilt.

[segment 1] A single vertical 9:16 clip that moves through 2 shots played one after another over time (a smoothly edited sequence with longer, gentle holds and soft transitions (each shot lingers, calm and unhurried)).
Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, minimal, graceful subject motion — not busy or energetic, even though cuts are quick.
Keep the SAME product identical in every shot — the product is: Lightweight Linen Open-Collar Summer Shirt, a men's summer shirt, lightweight linen, distinctive: open-collar, lightweight linen fabric. Its shape, packaging and colors must stay exactly the same across all shots.
Keep the same person consistent across every shot; exactly one person, no duplicate people.
The person speaks to the camera in English only, with natural, realistic lip-sync. Every spoken word is in English; never any other language, no gibberish.
Do not render any on-screen text, captions, subtitles, letters, words or watermarks; clean footage with no text overlay.
character: exceptionally attractive American man, highly photogenic celebrity-tier face, charismatic and witty 'it-guy' vibe, flawless model-tier features, magnetic viral TikToker appearance; product (keep identical in every shot): Lightweight Linen Open-Collar Summer Shirt, a men's summer shirt, lightweight linen, distinctive: open-collar, lightweight linen fabric; mood and tone: witty, effortless, breezy, charismatic; framing: vertical 9:16, subject large — upper body only by default; color grading matching this palette: sun-drenched beige, ocean blue, crisp white, warm golden hour; location: A sun-drenched luxury resort balcony overlooking a bright tropical beach; lighting: Bright, natural afternoon sunlight with a warm golden glow and soft, flattering shadows; mood: Breezy, vibrant, and effortlessly stylish summer vacation vibe; no on-screen text, captions, letters or watermarks
Shot 1: Medium-wide shot — the Lightweight Linen Open-Collar Summer Shirt product in focus, He steps back from the railing, unhurriedly rolling up one sleeve to forearm length. The open collar perfectly frames his relaxed posture as he turns his head to deliver a witty, charismatic grin.. Camera: Slow handheld orbit. The person says in English: "So lightweight for those resort days."
Shot 2: Close-up — the Lightweight Linen Open-Collar Summer Shirt product in focus, He smoothly slides on a pair of sleek sunglasses, playfully tapping the crisp linen chest of his shirt with two fingers. He gives a confident nod and points subtly toward the bottom edge of the screen.. Camera: Slow dolly out.
