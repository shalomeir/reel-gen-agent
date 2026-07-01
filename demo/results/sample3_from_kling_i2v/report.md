# 최종 리포트 — reference-users-shalomeir-devspaces-personalplayground-20260702-071804

## 유저 입력
- 목적: reference  /Users/shalomeir/DevSpaces/PersonalPlayground/beutyselection-ai-assignment/reel-gen-agent/reference_video/Spray._Glow._Repeat._Jelly_Serum_Mist_doing_its_thing_@yourgirl.vv_... [TikTok-7627503509855800607].mp4
영상 목적: BIODANCE Hydrating Collagen Water Full Essence Mist 숏폼 제품 광고
제품: BIODANCE Hydrating Collagen Water Full Essence Mist / 세안 후나 메이크업 전후에 뿌려 피부가 건조해 보이는 순간을 빠르게 정돈하는 수분 콜라겐 미스트 / sprayable facial essence mist for hydrating, anti-aging skincare routines / clean beauty-style facial mist bottle with a soft, fresh skincare look / skincare facial mist / hydrating collagen care, sprayable essence, morning routine friendly / spray onto face, hold bottle close to camera, show dewy skin finish
제품 URL: https://www.amazon.com/BIODANCE-Hydrating-Anti-Aging-Sprayable-Essentials/dp/B0GF86QJK7
제품 이미지: /Users/shalomeir/DevSpaces/PersonalPlayground/beutyselection-ai-assignment/reel-gen-agent/demo/sample_imgs/biodance-essence-mist-pink.png
캐릭터: mid-20s / female / strikingly beautiful young woman with fair luminous skin, smooth dewy glass-skin complexion, elegant oval face, refined symmetrical features, clear light blue-green eyes with a calm confident gaze, softly arched full brows, straight delicate nose, softly sculpted cheekbones, full natural rosy lips with a subtle polished pout, long sleek light brown hair parted cleanly in the center and tucked behind the ears, graceful long neck and defined collarbones, chic minimal beauty-model presence, photogenic and polished from close-up makeup-prep angles / slim graceful build with elegant shoulders, long neck, defined collarbones, and a refined fashion-beauty model silhouette / black sleeveless tank top, small chunky gold hoop earrings, delicate layered gold necklace, pale pink almond-shaped manicure, minimal clean makeup, fresh glossy skincare finish, elevated makeup-prep beauty routine styling
스타일: hyper_realistic
언어: en
- 제품: BIODANCE Collagen Peptides Jelly Serum Mist
- 레퍼런스: [TikTok-7627503509855800607].mp4

## 캐릭터
- age: mid-20s
- gender: female
- look: strikingly beautiful Caucasian woman with fair luminous skin, smooth dewy glass-skin complexion, elegant oval face, refined symmetrical features, clear light blue-green eyes, softly arched full brows, straight delicate nose, softly sculpted cheekbones, full natural rosy lips, long sleek light brown hair parted in the center, chic minimal beauty-model presence, top viral beauty influencer look

## 스타일
- tone: fresh, luminous, minimalist, elegant, dewy
- pacing: mixed
- motion: gentle
- palette: soft pink, black, gold, dewy peach, clean white

## 훅
- type: H4
- headline: Want this instant glass-skin glow?
- bottom_caption: Korean collagen jelly mist 💧
- visual: Extreme close-up of the creator's flawless, dewy cheek catching the light. She slowly turns to the camera, her clear blue-green eyes making direct contact, as her pale-pink manicured hand holds up the pink BIODANCE mist bottle.

## 스토리보드
- `00:00` [hook] — Extreme close-up of the creator's flawless, dewy cheek catching the light. She slowly turns to the camera, her clear blue-green eyes making direct contact, as her pale-pink manicured hand brings the pink BIODANCE mist bottle into frame. 자막:"Want this instant glass-skin glow?"
- `00:02` [demonstrate/use] — She closes her eyes, holding the pink bottle a few inches from her face, and sprays a continuous, fine mist. The mist elegantly envelops her face in the bright bathroom light. 자막:"Korean collagen jelly mist 💧"
- `00:04` [product_detail] — Macro detail of the fine misty droplets landing on her cheek, instantly absorbing and giving the skin a plump, wet, glass-like finish. 자막:"Plumping peptides"
- `00:07` [transformation] — She gently pats her cheeks with her pale-pink manicured hands, smiling softly as her skin looks visibly bouncy, deeply hydrated, and refreshed. 자막:"Deeply hydrating"
- `00:09` [proof/result] — She turns her head side to side, showing off the completely flawless, luminous glass-skin finish catching the light, her collarbones and sleek hair highlighting the elegant beauty aesthetic. 자막:"Flawless dewy finish"
- `00:11` [payoff/cta] — She holds the pink BIODANCE bottle right next to her glowing face, giving a confident, chic smile to the camera, gently tapping the bottle with one manicured finger. 자막:"Get your BIODANCE glow"

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
| 에셋 이미지 (캐릭터·제품·패키지·키비주얼(히어로 4K)) | gemini-3.1-pro-image-preview | 장 | 2 | $0.240 | $0.480 |
| 영상 클립 (6개 클립, 오디오 없음) | fal-ai/kling-video/o3/pro/image-to-video | 초 | 14 | $0.112 | $1.568 |
| BGM | lyria-3-pro-preview | 클립 | 1 | $0.040 | $0.040 |
| 나레이션 (대사 글자수 기준) | eleven_v3 | 1k자 | 0.138 | $0.180 | $0.025 |
| 품질 평가 (conformance + rubric) | gemini-2.5-flash | 호출 | 2 | $0.020 | $0.040 |
| 기획 LLM (추정: 약 10회 호출(입력~20k/출력~8k 토큰)) | gemini-3.1-pro-preview | 회차 | 1 | $0.136 | $0.136 |
| **합계** |  |  |  |  | **$2.769** |

- 단가는 공개 근사치(기준일 2026-07-01)이며 실제 청구와 다를 수 있음
- ken_burns/합성 BGM 등 로컬 폴백은 $0으로 계산
- 기획 LLM은 회차 휴리스틱 추정치(실제 토큰 사용량 관측 아님)
- 이미지는 히어로 4K 요율. 스틸(세그먼트/컷당 1장)과 에셋(캐릭터·제품·패키지·키비주얼) 모두 집계
- SFX는 플랜이 켰을 때만 집계(컷 sfx 큐 기준). Kling O3는 배선되면 자동 반영
- 재계획·재생성(run --max-iters) 반복 시 스틸/영상 비용은 회차당으로 곱해짐(1회 기준 추정)
- 미등록 모델(단가 미반영, $0 처리): gemini-3.1-pro-preview

## BGM
- 방식 gen, 모델 lyria-3-pro-preview
- 음악: 무드 fresh, luminous, elegant, 장르 clean modern downtempo, aquatic chillwave, 악기 warm rounded sub bass, soft filtered electric piano chords, crisp minimal electronic hi-hats, gentle atmospheric synth pads with a fluid, watery texture, 존재감 background

## 평가
- conformance: {'checks': [{'code': 'media.file_valid', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '파일 유효, ffprobe 파싱됨'}, {'code': 'media.container_complete', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '컨테이너 길이 정보 존재(잘림 없음)'}, {'code': 'media.video_decodable', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': '16 frames', 'detail': '프레임 디코드됨'}, {'code': 'media.audio_present', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '오디오 스트림 존재'}, {'code': 'media.aspect_ratio', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': '9:16', 'actual': '9:16', 'detail': None}, {'code': 'media.duration_positive', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': '13.867', 'detail': None}, {'code': 'media.resolution_min', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': '>= 480px wide', 'actual': '1080x1920', 'detail': None}, {'code': 'media.not_black', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'black ratio 0.00', 'detail': '정상 밝기 프레임 존재'}, {'code': 'media.not_frozen', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'adjacent diff 39.30', 'detail': '프레임 변화 있음'}, {'code': 'media.audio_not_silent', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'peak -2.05 dBFS', 'detail': '오디오 신호 존재'}, {'code': 'perceptual.volume_loudness', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': '-21.0 ~ -9.0 LUFS', 'actual': '-19.25 LUFS', 'detail': None}, {'code': 'perceptual.volume_no_clipping', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': '<= 0.0 dBTP', 'actual': '-2.05 dBFS', 'detail': None}, {'code': 'perceptual.cut_no_broken_frames', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '깨진 프레임 없음'}, {'code': 'perceptual.cut_transition_clean', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '영상에 명확한 결함이 없습니다.'}, {'code': 'perceptual.subtitle_in_safe_zone', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.subtitle_not_awkward', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.subtitle_legible', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.product_fit_purpose', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '제품이 목적에 맞게 표현됨'}, {'code': 'perceptual.model_appeal_fit', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '등장인물이 목적 전달에 적절'}, {'code': 'perceptual.subtitle_text_match', 'category': 'perceptual', 'intrinsic': False, 'status': 'skip', 'expected': None, 'actual': None, 'detail': '기대 자막 없음(레퍼런스/무자막)'}, {'code': 'perceptual.transition_as_specified', 'category': 'perceptual', 'intrinsic': False, 'status': 'skip', 'expected': None, 'actual': None, 'detail': '스토리보드 전환 타입 필드 추후'}], 'passed': True, 'counts': {'pass': 19, 'fail': 0, 'skip': 2}, 'source': {'path': 'outputs/reference-users-shalomeir-devspaces-personalplayground-20260702-071804/final.mp4', 'url': None, 'extractor_id': None}}
- rubric: {'dimensions': [{'code': 'D1', 'key': 'hook_strength', 'name': 'Hook 강도(첫 1~3초)', 'weight': 0.2, 'role': 'gate', 'score': 4, 'normalized': 0.75, 'rationale': "첫 3초 안에 '유리 피부 광채를 원하시나요?'라는 질문을 던져 시청자의 호기심을 자극하고 원하는 결과에 대한 기대감을 심어줍니다."}, {'code': 'D2', 'key': 'watch_completion', 'name': '시청 완결 설계', 'weight': 0.18, 'role': 'gate', 'score': 4, 'normalized': 0.75, 'rationale': "제품 사용 전후의 이상적인 모습과 함께 핵심 효능을 순차적으로 보여주며 시청자가 끝까지 시청하게 만듭니다. '듀이 피니쉬'로 마무리하며 제품의 효과를 다시 한번 강조합니다."}, {'code': 'D3', 'key': 'content_value', 'name': '콘텐츠 가치', 'weight': 0.15, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '제품이 제공하는 명확한 이점들(플럼핑, 깊은 수분 공급, 완벽한 이슬 광채)을 간결한 텍스트와 시각 자료로 전달하여 제품에 대한 정보를 효과적으로 제공합니다.'}, {'code': 'D4', 'key': 'brand_integration', 'name': '브랜드 통합 자연스러움', 'weight': 0.14, 'role': 'additive', 'score': 5, 'normalized': 1.0, 'rationale': '제품이 영상의 중심에 있으며, 제시된 문제(유리 피부)에 대한 해결책으로 자연스럽게 통합되어 광고라는 느낌 없이 제품의 효능을 부각합니다.'}, {'code': 'D5', 'key': 'call_to_action', 'name': '행동 유발 설계', 'weight': 0.14, 'role': 'additive', 'score': 3, 'normalized': 0.5, 'rationale': "명확하게 'BIODANCE 글로우를 얻으세요'라고 말하지만, 직접적인 구매 링크나 행동을 유도하는 더 강력한 CTA는 부재합니다."}, {'code': 'D6', 'key': 'platform_native', 'name': '플랫폼 네이티브성', 'weight': 0.09, 'role': 'additive', 'score': 3, 'normalized': 0.5, 'rationale': '세로형 비디오 포맷과 텍스트 오버레이를 사용하여 플랫폼에 적합하지만, 특별히 유행하는 사운드나 챌린지 형식을 활용하지는 않았습니다.'}, {'code': 'D7', 'key': 'trust_authenticity', 'name': '신뢰·진정성', 'weight': 0.1, 'role': 'additive', 'score': 3, 'normalized': 0.5, 'rationale': '모델의 완벽한 피부와 이상적인 결과에 초점을 맞춰 사실적인 공감대를 형성하기보다는 미학적인 부분에 더 집중하여 신뢰도가 다소 낮을 수 있습니다.'}], 'gate_coefficient': 0.5625, 'additive_core': 0.6734, 'gated_score': 37.88, 'flat_score': 70.25, 'gate_passed': True, 'passed': False, 'summary': "이 영상은 '바이오댄스 콜라겐 펩타이드 젤리 세럼 미스트'를 사용하여 유리 피부와 촉촉하고 탱탱한 피부를 얻는 과정을 시각적으로 보여주는 제품 광고입니다.", 'expected_effect': "이 비디오는 '유리 피부'와 '스킨케어'에 관심이 많은 20-30대 여성 시청자들의 이목을 끌 것입니다. 제품의 효능을 직접적으로 보여주므로, 즉각적인 피부 개선 효과를 원하는 잠재 구매자들이 제품 정보 탐색을 위해 영상을 시청할 가능성이 높습니다. 특정 뷰티 트렌드를 따르는 시청자들 사이에서 제품 인지도를 높이고 구매 전환율에 긍정적인 영향을 미칠 수 있지만, 강한 공유 동기가 부족하여 폭발적인 바이럴 효과보다는 꾸준한 유입을 기대할 수 있습니다.", 'source': {'path': 'outputs/reference-users-shalomeir-devspaces-personalplayground-20260702-071804/final.mp4', 'url': None, 'extractor_id': None}, 'scored': True}

## verify 교정(repair)
- 되돌린 횟수: 0
- 미해결 fail: 없음

## 바이럴 예측
(미작성)

## 노드별 프롬프트
### visuals
[segment 0] A single vertical 9:16 clip that moves through 4 shots played one after another over time (an edited sequence with varied pacing (a mix of longer holds and quicker cuts)).
Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, minimal, graceful subject motion — not busy or energetic, even though cuts are quick.
Keep the SAME product identical in every shot — the product is: BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mists, jelly serum mist, sprayable hydrogel. Its shape, packaging and colors must stay exactly the same across all shots.
Keep the same person consistent across every shot; exactly one person, no duplicate people.
The person is NOT talking: mouth relaxed and mostly closed, no lip movement, no speaking, no lip-sync. AUDIO: ambient and diegetic sounds only (room tone, product handling, fabric, water); absolutely NO voice, NO speech, NO dialogue, NO narration, NO singing, and no spoken words in any language. Voiceover is added separately.
Do not render any on-screen text, captions, subtitles, letters, words or watermarks; clean footage with no text overlay.
character: strikingly beautiful Caucasian woman with fair luminous skin, smooth dewy glass-skin complexion, elegant oval face, refined symmetrical features, clear light blue-green eyes, softly arched full brows, straight delicate nose, softly sculpted cheekbones, full natural rosy lips, long sleek light brown hair parted in the center, chic minimal beauty-model presence, top viral beauty influencer look; product (keep identical in every shot): BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mists, jelly serum mist, sprayable hydrogel; mood and tone: fresh, luminous, minimalist, elegant, dewy; framing: vertical 9:16, subject very large — tight on the face, from the upper chest up so the face fills most of the frame (face beauty product); color grading matching this palette: soft pink, black, gold, dewy peach, clean white; location: A bright, minimalist modern bathroom with a sleek white marble vanity and soft neutral tones, reflecting a premium clean beauty aesthetic; lighting: Soft, diffused natural morning daylight streaming through a large window, providing a gentle, flattering glow that perfectly highlights the luminous, dewy glass-skin finish; mood: Fresh, elegant, and rejuvenating, conveying a chic and effortless high-end morning skincare routine; no on-screen text, captions, letters or watermarks
Shot 1: Extreme Close-Up — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, Extreme close-up of the creator's flawless, dewy cheek catching the light. She slowly turns to the camera, her clear blue-green eyes making direct contact, as her pale-pink manicured hand holds up the pink BIODANCE mist bottle.. Camera: Slow push-in.
Shot 2: Medium Close-Up — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, She closes her eyes, holding the pink bottle a few inches from her face, and sprays a continuous, fine mist. The mist elegantly envelops her face in the bright bathroom light.. Camera: Subtle orbit left.
Shot 3: Macro Detail — the creator, Macro detail of the fine misty droplets landing on her cheek, instantly absorbing and giving the skin a plump, wet, glass-like finish.. Camera: Slow macro pan.
Shot 4: Close-Up — the creator, She gently pats her cheeks with her pale-pink manicured hands, smiling softly as her skin looks visibly bouncy, deeply hydrated, and refreshed.. Camera: Handheld slight push-in.

[segment 1] A single vertical 9:16 clip that moves through 2 shots played one after another over time (an edited sequence with varied pacing (a mix of longer holds and quicker cuts)).
Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, minimal, graceful subject motion — not busy or energetic, even though cuts are quick.
Keep the SAME product identical in every shot — the product is: BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mists, jelly serum mist, sprayable hydrogel. Its shape, packaging and colors must stay exactly the same across all shots.
Keep the same person consistent across every shot; exactly one person, no duplicate people.
The person is NOT talking: mouth relaxed and mostly closed, no lip movement, no speaking, no lip-sync. AUDIO: ambient and diegetic sounds only (room tone, product handling, fabric, water); absolutely NO voice, NO speech, NO dialogue, NO narration, NO singing, and no spoken words in any language. Voiceover is added separately.
Do not render any on-screen text, captions, subtitles, letters, words or watermarks; clean footage with no text overlay.
character: strikingly beautiful Caucasian woman with fair luminous skin, smooth dewy glass-skin complexion, elegant oval face, refined symmetrical features, clear light blue-green eyes, softly arched full brows, straight delicate nose, softly sculpted cheekbones, full natural rosy lips, long sleek light brown hair parted in the center, chic minimal beauty-model presence, top viral beauty influencer look; product (keep identical in every shot): BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mists, jelly serum mist, sprayable hydrogel; mood and tone: fresh, luminous, minimalist, elegant, dewy; framing: vertical 9:16, subject very large — tight on the face, from the upper chest up so the face fills most of the frame (face beauty product); color grading matching this palette: soft pink, black, gold, dewy peach, clean white; location: A bright, minimalist modern bathroom with a sleek white marble vanity and soft neutral tones, reflecting a premium clean beauty aesthetic; lighting: Soft, diffused natural morning daylight streaming through a large window, providing a gentle, flattering glow that perfectly highlights the luminous, dewy glass-skin finish; mood: Fresh, elegant, and rejuvenating, conveying a chic and effortless high-end morning skincare routine; no on-screen text, captions, letters or watermarks
Shot 1: Medium Shot — the creator, She turns her head side to side, showing off the completely flawless, luminous glass-skin finish catching the light, her collarbones and sleek hair highlighting the elegant beauty aesthetic.. Camera: Slow arc shot.
Shot 2: Medium Close-Up — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, She holds the pink BIODANCE bottle right next to her glowing face, giving a confident, chic smile to the camera, gently tapping the bottle with one manicured finger.. Camera: Quick zoom to product.
