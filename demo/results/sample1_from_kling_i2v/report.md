# 최종 리포트 — biodance-biodance-hydrating-collagen-water-20260702-071214

## 유저 입력
- 목적: 영상 목적: BIODANCE 콜라겐 미스트를 자연스럽게 소개하는 세로 숏폼 영상
제품: BIODANCE Hydrating Collagen Water Full Essence Mist / 세안 후나 메이크업 전후에 뿌려 피부가 건조해 보이는 순간을 빠르게 정돈하는 수분 콜라겐 미스트 / sprayable facial essence mist for hydrating, anti-aging skincare routines / clean beauty-style facial mist bottle with a soft, fresh skincare look / skincare facial mist / hydrating collagen care, sprayable essence, morning routine friendly / spray onto face, hold bottle close to camera, show dewy skin finish
제품 URL: https://www.amazon.com/BIODANCE-Hydrating-Anti-Aging-Sprayable-Essentials/dp/B0GF86QJK7
제품 이미지: /Users/shalomeir/DevSpaces/PersonalPlayground/beutyselection-ai-assignment/reel-gen-agent/demo/sample_imgs/biodance-essence-mist-pink.png
캐릭터: mid-20s / female / beauty creator
스타일: hyper_realistic
언어: en
- 제품: BIODANCE Collagen Peptides Jelly Serum Mist
- 레퍼런스: -

## 캐릭터
- age: mid-20s
- gender: female
- look: exceptionally attractive American woman, top viral beauty influencer, flawless dewy skin, model-tier, magnetic and highly photogenic aspirational it-girl

## 스타일
- tone: aspirational, fresh, dewy, aesthetic, authentic
- pacing: fast_montage
- motion: gentle
- palette: soft pink, dewy peach, clean white, warm beige

## 훅
- type: H2
- headline: Want this flawless, dewy glass skin?
- bottom_caption: my secret to instant plumpness ✨
- visual: Extreme close-up of the creator's flawless, wet-looking glowing face. She slowly turns her head to catch the studio light perfectly on her cheekbones, holding the aesthetic pink BIODANCE bottle near her chin.

## 스토리보드
- `00:00` [hook] — Creator slowly turns her head to catch the studio light perfectly on her cheekbones, holding the aesthetic pink BIODANCE bottle near her chin. 자막:"Want this flawless, dewy glass skin?"
- `00:01` [tension/problem] — Creator dramatically pokes a dull, dry patch on her cheek while looking in the bathroom mirror, showing slight frustration. 자막:"Dull, dry moments happen..."
- `00:02` [establish] — Camera whips down to the aesthetic pink BIODANCE bottle resting prominently on the sleek marble vanity. 자막:"My secret to instant plumpness ✨"
- `00:03` [demonstrate] — A finger presses the nozzle in macro detail, spraying a fine cloud of hydrogel mist directly toward the camera lens. 자막:"BIODANCE Jelly Serum Mist"
- `00:04` [use] — Creator holds the bottle close to her face and sprays generously, her eyes closed in deep relaxation. 자막:"Collagen peptide hydrogel"
- `00:05` [use] — Creator quickly and briskly pats her cheeks with both hands, working the dewy essence into her skin. 자막:"Instantly hydrates"
- `00:07` [proof] — Creator presses a finger into her cheek to reveal extreme bounce and a highly reflective, wet-looking glow. 자막:"Look at that bounce!"
- `00:08` [demonstrate] — Creator applies a quick swipe of lip gloss over her perfectly prepped, dewy skin. 자막:"Perfect makeup prep"
- `00:09` [use] — She gives her face one final quick spritz with the pink bottle for a finishing touch. 자막:"Or a dewy finish"
- `00:10` [lifestyle] — Creator casually tosses the pink bottle into a stylish travel makeup bag on the counter. 자막:"Travel friendly"
- `00:11` [transformation] — Creator looks into the vanity mirror, giving a confident hair flip with her radiantly glowing skin. 자막:"Flawless all day"
- `00:12` [payoff/cta] — Creator holds the pink BIODANCE bottle out directly to the camera with a bright, enthusiastic smile. 자막:"Get yours today!"

## 최종 의견
(미작성)

## 노드 흐름
production_plan -> stills -> visuals -> voice -> bgm -> sfx -> assemble -> verify -> describe -> evaluate

## 사용 모델
video=fal-ai/kling-video/o3/pro/image-to-video, image_still=gemini-3.1-pro-image-preview, image_asset=gemini-3.1-pro-image-preview, bgm=lyria-3-pro-preview, tts=eleven_v3, llm=gemini-3.1-pro-preview

## 예상 비용 (단가 기준일 2026-07-01, USD, 실제 청구와 다를 수 있음)

| 항목 | 모델 | 단위 | 사용량 | 단가 | 소계 |
|---|---|---|---|---|---|
| 패널 스틸 (세그먼트당 1장(히어로 4K)) | gemini-3.1-pro-image-preview | 장 | 2 | $0.240 | $0.480 |
| 에셋 이미지 (캐릭터·제품·패키지·키비주얼(히어로 4K)) | gemini-3.1-pro-image-preview | 장 | 3 | $0.240 | $0.720 |
| 영상 클립 (12개 클립, 오디오 없음) | fal-ai/kling-video/o3/pro/image-to-video | 초 | 14 | $0.112 | $1.568 |
| BGM | lyria-3-pro-preview | 클립 | 1 | $0.040 | $0.040 |
| 나레이션 (대사 글자수 기준) | eleven_v3 | 1k자 | 0.156 | $0.180 | $0.028 |
| SFX (효과음 큐 있는 컷 수 기준) | elevenlabs-sfx | 클립 | 4 | $0.080 | $0.320 |
| 품질 평가 (conformance + rubric) | gemini-2.5-flash | 호출 | 2 | $0.020 | $0.040 |
| 기획 LLM (추정: 약 10회 호출(입력~20k/출력~8k 토큰)) | gemini-3.1-pro-preview | 회차 | 1 | $0.136 | $0.136 |
| **합계** |  |  |  |  | **$3.332** |

- 단가는 공개 근사치(기준일 2026-07-01)이며 실제 청구와 다를 수 있음
- ken_burns/합성 BGM 등 로컬 폴백은 $0으로 계산
- 기획 LLM은 회차 휴리스틱 추정치(실제 토큰 사용량 관측 아님)
- 이미지는 히어로 4K 요율. 스틸(세그먼트/컷당 1장)과 에셋(캐릭터·제품·패키지·키비주얼) 모두 집계
- SFX는 플랜이 켰을 때만 집계(컷 sfx 큐 기준). Kling O3는 배선되면 자동 반영
- 재계획·재생성(run --max-iters) 반복 시 스틸/영상 비용은 회차당으로 곱해짐(1회 기준 추정)
- 미등록 모델(단가 미반영, $0 처리): gemini-3.1-pro-preview

## BGM
- 방식 gen, 모델 lyria-3-pro-preview
- 음악: 무드 aspirational, fresh, chic, driving, 장르 clean liquid deep house, modern aesthetic electronic, 악기 warm rolling sub bass, crisp minimal hi-hats, soft filtered electric piano chords, bright FM synth plucks mimicking water droplets, gentle rhythmic shakers, 존재감 prominent

## 평가
- conformance: {'checks': [{'code': 'media.file_valid', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '파일 유효, ffprobe 파싱됨'}, {'code': 'media.container_complete', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '컨테이너 길이 정보 존재(잘림 없음)'}, {'code': 'media.video_decodable', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': '16 frames', 'detail': '프레임 디코드됨'}, {'code': 'media.audio_present', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '오디오 스트림 존재'}, {'code': 'media.aspect_ratio', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': '9:16', 'actual': '9:16', 'detail': None}, {'code': 'media.duration_positive', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': '14.0', 'detail': None}, {'code': 'media.resolution_min', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': '>= 480px wide', 'actual': '1080x1920', 'detail': None}, {'code': 'media.not_black', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'black ratio 0.00', 'detail': '정상 밝기 프레임 존재'}, {'code': 'media.not_frozen', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'adjacent diff 46.95', 'detail': '프레임 변화 있음'}, {'code': 'media.audio_not_silent', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'peak -2.09 dBFS', 'detail': '오디오 신호 존재'}, {'code': 'perceptual.volume_loudness', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': '-21.0 ~ -9.0 LUFS', 'actual': '-18.49 LUFS', 'detail': None}, {'code': 'perceptual.volume_no_clipping', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': '<= 0.0 dBTP', 'actual': '-2.09 dBFS', 'detail': None}, {'code': 'perceptual.cut_no_broken_frames', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '깨진 프레임 없음'}, {'code': 'perceptual.cut_transition_clean', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '자막이 안전 영역을 벗어나 일부 잘리며, 일부 자막이 제품과 모델 얼굴을 가립니다.'}, {'code': 'perceptual.subtitle_in_safe_zone', 'category': 'perceptual', 'intrinsic': True, 'status': 'fail', 'expected': None, 'actual': None, 'detail': '자막이 화면 밖/UI 영역 침범'}, {'code': 'perceptual.subtitle_not_awkward', 'category': 'perceptual', 'intrinsic': True, 'status': 'fail', 'expected': None, 'actual': None, 'detail': '자막이 피사체/제품을 가림'}, {'code': 'perceptual.subtitle_legible', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.product_fit_purpose', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '제품이 목적에 맞게 표현됨'}, {'code': 'perceptual.model_appeal_fit', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '등장인물이 목적 전달에 적절'}, {'code': 'perceptual.subtitle_text_match', 'category': 'perceptual', 'intrinsic': False, 'status': 'skip', 'expected': None, 'actual': None, 'detail': '기대 자막 없음(레퍼런스/무자막)'}, {'code': 'perceptual.transition_as_specified', 'category': 'perceptual', 'intrinsic': False, 'status': 'skip', 'expected': None, 'actual': None, 'detail': '스토리보드 전환 타입 필드 추후'}], 'passed': False, 'counts': {'pass': 17, 'fail': 2, 'skip': 2}, 'source': {'path': 'outputs/biodance-biodance-hydrating-collagen-water-20260702-071214/final.mp4', 'url': None, 'extractor_id': None}}
- rubric: {'dimensions': [{'code': 'D1', 'key': 'hook_strength', 'name': 'Hook 강도(첫 1~3초)', 'weight': 0.2, 'role': 'gate', 'score': 5, 'normalized': 1.0, 'rationale': '촉촉하고 빛나는 피부를 즉시 보여주며 "이런 피부를 원하세요?"라고 직접적으로 묻는 강력한 시각적/질문형 후킹입니다.'}, {'code': 'D2', 'key': 'watch_completion', 'name': '시청 완결 설계', 'weight': 0.18, 'role': 'gate', 'score': 5, 'normalized': 1.0, 'rationale': '제품 사용 과정과 명확한 효과를 빠르게 보여주며 흥미를 유지시키고, 시종일관 동일한 톤앤매너로 영상의 흐름을 놓치지 않게 합니다.'}, {'code': 'D3', 'key': 'content_value', 'name': '콘텐츠 가치', 'weight': 0.15, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '제품의 주요 성분(콜라겐 펩타이드 하이드로겔)과 효능(즉각적인 볼륨, 수분 공급, 메이크업 준비)을 명확히 전달하여 유용한 정보를 제공합니다.'}, {'code': 'D4', 'key': 'brand_integration', 'name': '브랜드 통합 자연스러움', 'weight': 0.14, 'role': 'additive', 'score': 5, 'normalized': 1.0, 'rationale': '제품이 영상의 핵심 주제이며, 원하는 피부를 얻기 위한 명확한 해결책으로 자연스럽게 제시되어 있습니다.'}, {'code': 'D5', 'key': 'call_to_action', 'name': '행동 유발 설계', 'weight': 0.14, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '영상 말미에 "오늘 구매하세요!"라는 직접적인 구매 유도 문구가 명확하게 제시됩니다.'}, {'code': 'D6', 'key': 'platform_native', 'name': '플랫폼 네이티브성', 'weight': 0.09, 'role': 'additive', 'score': 5, 'normalized': 1.0, 'rationale': '숏폼 플랫폼에 최적화된 빠른 편집, 텍스트 오버레이, 경쾌한 배경 음악 등 트렌디한 형식을 잘 활용했습니다.'}, {'code': 'D7', 'key': 'trust_authenticity', 'name': '신뢰·진정성', 'weight': 0.1, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '모델의 피부 상태가 좋아 보이고, 제품의 즉각적인 보습 및 탄력 개선 효과는 실제 가능성이 있어 과장된 느낌이 적습니다.'}], 'gate_coefficient': 1.0, 'additive_core': 0.8427, 'gated_score': 84.27, 'flat_score': 90.25, 'gate_passed': True, 'passed': True, 'summary': '생기 잃은 피부에 즉각적인 수분과 탄력을 선사하는 콜라겐 젤리 미스트의 효과를 강조하는 제품 광고입니다.', 'expected_effect': '이 영상은 \'유리알 피부\'나 \'물광 피부\'에 관심 있는 20~40대 여성들을 주 타겟으로 하여 높은 시청 완료율을 보일 것입니다. 제품 사용 전후의 극명한 대비와 즉각적인 효과 강조는 구매 욕구를 자극하며, "나도 저런 피부가 되고 싶다"는 공감대를 형성하여 공유 및 저장으로 이어질 가능성이 높습니다. 특히 건조하고 푸석한 피부로 고민하는 시청자들에게는 솔루션을 제시하는 영상으로 인식되어 높은 도달률과 전환율을 기대할 수 있습니다.', 'source': {'path': 'outputs/biodance-biodance-hydrating-collagen-water-20260702-071214/final.mp4', 'url': None, 'extractor_id': None}, 'scored': True}

## verify 교정(repair)
- 되돌린 횟수: 0
- 미해결 fail: ['perceptual.subtitle_in_safe_zone', 'perceptual.subtitle_not_awkward']

## 바이럴 예측
(미작성)

## 노드별 프롬프트
### visuals
[segment 0] A single vertical 9:16 clip that moves through 8 shots played one after another over time (a fast-edited sequence with hard, snappy cuts on a tight timeline (each shot brief and driving)).
Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, minimal, graceful subject motion — not busy or energetic, even though cuts are quick.
Keep the SAME product identical in every shot — the product is: BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mist, Jelly Serum Mist, Sprayable Hydrogel, in a Mist bottle. Its shape, packaging and colors must stay exactly the same across all shots.
Keep the same person consistent across every shot; exactly one person, no duplicate people.
The person is NOT talking: mouth relaxed and mostly closed, no lip movement, no speaking, no lip-sync. AUDIO: ambient and diegetic sounds only (room tone, product handling, fabric, water); absolutely NO voice, NO speech, NO dialogue, NO narration, NO singing, and no spoken words in any language. Voiceover is added separately.
Do not render any on-screen text, captions, subtitles, letters, words or watermarks; clean footage with no text overlay.
character: exceptionally attractive American woman, top viral beauty influencer, flawless dewy skin, model-tier, magnetic and highly photogenic aspirational it-girl; product (keep identical in every shot): BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mist, Jelly Serum Mist, Sprayable Hydrogel, in a Mist bottle; mood and tone: dewy, aspirational, refreshing, authentic, chic; framing: vertical 9:16, subject very large — tight on the face, from the upper chest up so the face fills most of the frame (face beauty product); color grading matching this palette: soft pink, dewy peach, clean white, warm beige; location: A modern, aesthetic bathroom with a sleek vanity and a large mirror; lighting: Soft, diffused natural morning sunlight mixed with flattering vanity lights; mood: Fresh, clean, aspirational, and radiant; no on-screen text, captions, letters or watermarks
Shot 1: Extreme Close-Up — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, Extreme close-up of the creator's flawless, wet-looking glowing face. She slowly turns her head to catch the studio light perfectly on her cheekbones, holding the aesthetic pink BIODANCE bottle near her chin.. Camera: slow push-in.
Shot 2: Medium Close-Up — the creator, Creator dramatically pokes a dull, dry patch on her cheek while looking in the bathroom mirror, showing slight frustration.. Camera: quick zoom out.
Shot 3: Close-Up — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, Camera whips down to the aesthetic pink BIODANCE bottle resting prominently on the sleek marble vanity.. Camera: whip-pan.
Shot 4: Macro Detail — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, A finger presses the nozzle in macro detail, spraying a fine cloud of hydrogel mist directly toward the camera lens.. Camera: static.
Shot 5: Medium Shot — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, Creator holds the bottle close to her face and sprays generously, her eyes closed in deep relaxation.. Camera: handheld orbit.
Shot 6: Close-Up — the creator, Creator quickly and briskly pats her cheeks with both hands, working the dewy essence into her skin.. Camera: tilt up.
Shot 7: Extreme Close-Up — the creator, Creator presses a finger into her cheek to reveal extreme bounce and a highly reflective, wet-looking glow.. Camera: slow push-in.
Shot 8: Medium Close-Up — the creator, Creator applies a quick swipe of lip gloss over her perfectly prepped, dewy skin.. Camera: pan right.

[segment 1] A single vertical 9:16 clip that moves through 4 shots played one after another over time (a fast-edited sequence with hard, snappy cuts on a tight timeline (each shot brief and driving)).
Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, minimal, graceful subject motion — not busy or energetic, even though cuts are quick.
Keep the SAME product identical in every shot — the product is: BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mist, Jelly Serum Mist, Sprayable Hydrogel, in a Mist bottle. Its shape, packaging and colors must stay exactly the same across all shots.
Keep the same person consistent across every shot; exactly one person, no duplicate people.
The person is NOT talking: mouth relaxed and mostly closed, no lip movement, no speaking, no lip-sync. AUDIO: ambient and diegetic sounds only (room tone, product handling, fabric, water); absolutely NO voice, NO speech, NO dialogue, NO narration, NO singing, and no spoken words in any language. Voiceover is added separately.
Do not render any on-screen text, captions, subtitles, letters, words or watermarks; clean footage with no text overlay.
character: exceptionally attractive American woman, top viral beauty influencer, flawless dewy skin, model-tier, magnetic and highly photogenic aspirational it-girl; product (keep identical in every shot): BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mist, Jelly Serum Mist, Sprayable Hydrogel, in a Mist bottle; mood and tone: dewy, aspirational, refreshing, authentic, chic; framing: vertical 9:16, subject very large — tight on the face, from the upper chest up so the face fills most of the frame (face beauty product); color grading matching this palette: soft pink, dewy peach, clean white, warm beige; location: A modern, aesthetic bathroom with a sleek vanity and a large mirror; lighting: Soft, diffused natural morning sunlight mixed with flattering vanity lights; mood: Fresh, clean, aspirational, and radiant; no on-screen text, captions, letters or watermarks
Shot 1: Close-Up — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, She gives her face one final quick spritz with the pink bottle for a finishing touch.. Camera: quick zoom in.
Shot 2: POV — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, Creator casually tosses the pink bottle into a stylish travel makeup bag on the counter.. Camera: tilt down.
Shot 3: Medium Shot — the creator, Creator looks into the vanity mirror, giving a confident hair flip with her radiantly glowing skin.. Camera: arc left.
Shot 4: Close-Up — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, Creator holds the pink BIODANCE bottle out directly to the camera with a bright, enthusiastic smile.. Camera: push-in.
