# 최종 리포트 — biodance-biodance-hydrating-collagen-water-20260702-012954

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
- look: American (Western), exceptionally attractive, flawless dewy skin, top viral beauty influencer and TikToker aesthetic, celebrity-tier face, model-tier, magnetic and highly photogenic, aspirational 'it-girl' look

## 스타일
- tone: luminous, fresh, aspirational, chic
- pacing: mixed
- motion: gentle
- palette: soft pink, luminous white, dewy peach, warm sunlight

## 훅
- type: H3
- headline: Want that instant glass skin glow?
- bottom_caption: My anti-aging collagen secret ✨
- visual: Extreme close-up of her flawless, dewy face catching the natural light. She smiles slightly, holding the chic pink BIODANCE mist bottle next to her cheek, and gives it a slow, cinematic spritz that creates a luminous halo.

## 스토리보드
- `00:00` [hook / establish] — Her flawless, dewy face catches the natural light. She smiles slightly, holding the chic pink BIODANCE mist bottle next to her cheek, and gives it a slow, cinematic spritz that creates a luminous halo. 자막:"Want that instant glass skin glow?"
- `00:02` [tension / problem] — Standing at her chic bathroom vanity, she taps her bare cheek with a slight pout to indicate dry, dull morning skin, then eagerly grabs the pink mist bottle. 자막:"Morning skin feeling dry and dull?"
- `00:04` [demonstrate / use] — The fine mist sprays directly onto her cheek, visibly coating the skin in a rich, hydrating jelly-to-liquid layer that glistens instantly. 자막:"Collagen peptide jelly serum!"
- `00:07` [transformation] — She gently presses and pats the essence into her skin with both hands, her expression shifting to pure delight as her face visibly plumps up. 자막:"Instantly plumps & hydrates 💦"
- `00:09` [proof / result] — Looking into her vanity mirror, she turns her head side to side, showing off the radiant, flawless glass-skin reflection catching the warm bathroom lights. 자막:"The ultimate anti-aging secret ✨"
- `00:11` [payoff / cta] — She winks at the camera with a confident smile, holding the BIODANCE bottle right up to the lens and tapping the pink cap playfully with her perfectly manicured finger. 자막:"Get your BIODANCE glow on Amazon!"

## 최종 의견
(미작성)

## 노드 흐름
production_plan -> stills -> visuals -> voice -> bgm -> sfx -> assemble -> verify -> describe -> evaluate

## 사용 모델
video=veo-3.1-fast-generate-001

## 예상 비용 (단가 기준일 2026-07-01, USD, 실제 청구와 다를 수 있음)

| 항목 | 모델 | 단위 | 사용량 | 단가 | 소계 |
|---|---|---|---|---|---|
| 패널 스틸 (스틸 있는 패널 수 기준) | gemini-3.1-pro-image-preview | 장 | 2 | $0.120 | $0.240 |
| 영상 클립 (6개 클립) | veo-3.1-fast-generate-001 | 초 | 14 | $0.150 | $2.100 |
| BGM | lyria-3-pro-preview | 클립 | 1 | $0.040 | $0.040 |
| 나레이션 (대사 글자수 기준) | eleven_v3 | 1k자 | 0.132 | $0.180 | $0.024 |
| 품질 평가 (conformance + rubric) | gemini-2.5-flash | 호출 | 2 | $0.020 | $0.040 |
| **합계** |  |  |  |  | **$2.444** |

- 단가는 공개 근사치(기준일 2026-07-01)이며 실제 청구와 다를 수 있음
- ken_burns/합성 BGM 등 로컬 폴백은 $0으로 계산
- 기획·카피 텍스트 LLM(컨셉/훅/스토리보드/대사)은 별도 planning 단계라 미포함
- SFX는 플랜이 켰을 때만 집계(컷 sfx 큐 기준). Kling O3는 배선되면 자동 반영
- 이미지 수는 스틸 있는 패널 기준 추정(사용자 제공 스틸이 섞일 수 있음)

## BGM
- 방식 gen, 모델 lyria-3-pro-preview
- 음악: 무드 luminous, chic, aspirational, 장르 clean modern chillwave and ambient R&B instrumental, 악기 warm rolling sub-bass, lush atmospheric synth pads, crisp minimal hi-hats, shimmering bell accents, soft rhythmic snaps, 존재감 background

## 평가
- conformance: {'checks': [{'code': 'media.file_valid', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '파일 유효, ffprobe 파싱됨'}, {'code': 'media.container_complete', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '컨테이너 길이 정보 존재(잘림 없음)'}, {'code': 'media.video_decodable', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': '16 frames', 'detail': '프레임 디코드됨'}, {'code': 'media.audio_present', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '오디오 스트림 존재'}, {'code': 'media.aspect_ratio', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': '9:16', 'actual': '9:16', 'detail': None}, {'code': 'media.duration_positive', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': '14.101', 'detail': None}, {'code': 'media.resolution_min', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': '>= 480px wide', 'actual': '1080x1920', 'detail': None}, {'code': 'media.not_black', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'black ratio 0.00', 'detail': '정상 밝기 프레임 존재'}, {'code': 'media.not_frozen', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'adjacent diff 39.03', 'detail': '프레임 변화 있음'}, {'code': 'media.audio_not_silent', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'peak -3.99 dBFS', 'detail': '오디오 신호 존재'}, {'code': 'perceptual.volume_loudness', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': '-21.0 ~ -9.0 LUFS', 'actual': '-19.47 LUFS', 'detail': None}, {'code': 'perceptual.volume_no_clipping', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': '<= 0.0 dBTP', 'actual': '-3.99 dBFS', 'detail': None}, {'code': 'perceptual.cut_no_broken_frames', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '깨진 프레임 없음'}, {'code': 'perceptual.cut_transition_clean', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '영상에 명확한 결함이 없습니다.'}, {'code': 'perceptual.subtitle_in_safe_zone', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.subtitle_not_awkward', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.subtitle_legible', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.product_fit_purpose', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '제품이 목적에 맞게 표현됨'}, {'code': 'perceptual.model_appeal_fit', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '등장인물이 목적 전달에 적절'}, {'code': 'perceptual.subtitle_text_match', 'category': 'perceptual', 'intrinsic': False, 'status': 'skip', 'expected': None, 'actual': None, 'detail': '기대 자막 없음(레퍼런스/무자막)'}, {'code': 'perceptual.transition_as_specified', 'category': 'perceptual', 'intrinsic': False, 'status': 'skip', 'expected': None, 'actual': None, 'detail': '스토리보드 전환 타입 필드 추후'}], 'passed': True, 'counts': {'pass': 19, 'fail': 0, 'skip': 2}, 'source': {'path': 'outputs/biodance-biodance-hydrating-collagen-water-20260702-012954/final.mp4', 'url': None, 'extractor_id': None}}
- rubric: {'dimensions': [{'code': 'D1', 'key': 'hook_strength', 'name': 'Hook 강도(첫 1~3초)', 'weight': 0.2, 'role': 'gate', 'score': 4, 'normalized': 0.75, 'rationale': '촉촉하고 빛나는 피부 클로즈업과 질문으로 시청자의 시선을 빠르게 끈다.'}, {'code': 'D2', 'key': 'watch_completion', 'name': '시청 완결 설계', 'weight': 0.18, 'role': 'gate', 'score': 4, 'normalized': 0.75, 'rationale': '문제 제기, 제품 소개, 사용감, 효과, 구매 유도까지 자연스러운 흐름으로 몰입감을 유지한다.'}, {'code': 'D3', 'key': 'content_value', 'name': '콘텐츠 가치', 'weight': 0.15, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '제품의 독특한 제형과 핵심적인 효과를 명확하게 보여주어 정보 가치가 높다.'}, {'code': 'D4', 'key': 'brand_integration', 'name': '브랜드 통합 자연스러움', 'weight': 0.14, 'role': 'additive', 'score': 5, 'normalized': 1.0, 'rationale': '제품이 영상의 시작부터 끝까지 자연스럽게 노출되며, 메시지와 완벽하게 통합되어 있다.'}, {'code': 'D5', 'key': 'call_to_action', 'name': '행동 유발 설계', 'weight': 0.14, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '마지막에 아마존 구매를 유도하는 명확한 CTA가 있어 구매 전환 가능성을 높인다.'}, {'code': 'D6', 'key': 'platform_native', 'name': '플랫폼 네이티브성', 'weight': 0.09, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '짧은 길이, 세로 포맷, 텍스트 오버레이 등 숏폼 플랫폼에 최적화된 구성을 보여준다.'}, {'code': 'D7', 'key': 'trust_authenticity', 'name': '신뢰·진정성', 'weight': 0.1, 'role': 'additive', 'score': 3, 'normalized': 0.5, 'rationale': '제품 사용 후 피부가 촉촉해 보이는 것은 설득력 있으나, "궁극의 안티에이징 비밀"과 같은 표현은 다소 과장되어 신뢰도를 약간 낮춘다.'}], 'gate_coefficient': 0.5625, 'additive_core': 0.7661, 'gated_score': 43.09, 'flat_score': 76.0, 'gate_passed': True, 'passed': True, 'summary': '콜라겐 펩타이드 젤리 미스트의 독특한 제형과 즉각적인 보습 및 탄력 효과를 강조하는 숏폼 광고 영상.', 'expected_effect': '피부 건조함과 탄력 저하에 고민이 있는 20-40대 여성 시청자들이 주목할 것이다. 제품의 신기한 젤리 제형과 즉각적인 윤광 효과 덕분에 "저장" 버튼을 눌러 나중에 찾아보거나, 유사한 고민을 가진 친구에게 "공유"할 가능성이 높다. 아마존 구매 CTA가 있어 일정 부분 구매 전환을 유도하며, 제품 인지도를 높이는 데 효과적일 것으로 예상된다.', 'source': {'path': 'outputs/biodance-biodance-hydrating-collagen-water-20260702-012954/final.mp4', 'url': None, 'extractor_id': None}, 'scored': True}

## verify 교정(repair)
- 되돌린 횟수: 0
- 미해결 fail: 없음

## 바이럴 예측
(미작성)

## 노드별 프롬프트
### visuals
[segment 0] A single vertical 9:16 clip that moves through 3 shots played one after another over time (an edited sequence with varied pacing (a mix of longer holds and quicker cuts)).
Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, minimal, graceful subject motion — not busy or energetic, even though cuts are quick.
Keep the SAME product identical in every shot — the product is: BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mists, Jelly Serum Mist, Sprayable Hydrogel, in a Sprayable bottle, distinctive: Jelly serum texture, Sprayable format, Hydrogel composition. Its shape, packaging and colors must stay exactly the same across all shots.
Keep the same person consistent across every shot; exactly one person, no duplicate people.
The person is NOT talking: mouth relaxed and mostly closed, no lip movement, no speaking, no lip-sync. AUDIO: ambient and diegetic sounds only (room tone, product handling, fabric, water); absolutely NO voice, NO speech, NO dialogue, NO narration, NO singing, and no spoken words in any language. Voiceover is added separately.
Do not render any on-screen text, captions, subtitles, letters, words or watermarks; clean footage with no text overlay.
character: American (Western), exceptionally attractive, flawless dewy skin, top viral beauty influencer and TikToker aesthetic, celebrity-tier face, model-tier, magnetic and highly photogenic, aspirational 'it-girl' look; product (keep identical in every shot): BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mists, Jelly Serum Mist, Sprayable Hydrogel, in a Sprayable bottle, distinctive: Jelly serum texture, Sprayable format, Hydrogel composition; mood and tone: fresh, luminous, aspirational, chic; framing: vertical 9:16, subject very large — tight on the face, from the upper chest up so the face fills most of the frame (face beauty product); color grading matching this palette: soft pink, dewy white, warm beige, glassy clear; location: A chic, modern bathroom vanity with minimalist decor, perfect for an aspirational morning skincare routine; lighting: Soft, diffused morning natural light combined with a flattering front fill light to accentuate a flawless, dewy skin glow; mood: Fresh, radiant, and effortlessly trendy, capturing the aspirational 'clean girl' TikTok aesthetic; no on-screen text, captions, letters or watermarks
Shot 1: Extreme Close-Up — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, Her flawless, dewy face catches the natural light. She smiles slightly, holding the chic pink BIODANCE mist bottle next to her cheek, and gives it a slow, cinematic spritz that creates a luminous halo.. Camera: Slow push-in.
Shot 2: Medium Shot — the creator, Standing at her chic bathroom vanity, she taps her bare cheek with a slight pout to indicate dry, dull morning skin, then eagerly grabs the pink mist bottle.. Camera: Handheld orbit.
Shot 3: Macro Detail — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, The fine mist sprays directly onto her cheek, visibly coating the skin in a rich, hydrating jelly-to-liquid layer that glistens instantly.. Camera: Quick zoom.

[segment 1] A single vertical 9:16 clip that moves through 3 shots played one after another over time (an edited sequence with varied pacing (a mix of longer holds and quicker cuts)).
Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, minimal, graceful subject motion — not busy or energetic, even though cuts are quick.
Keep the SAME product identical in every shot — the product is: BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mists, Jelly Serum Mist, Sprayable Hydrogel, in a Sprayable bottle, distinctive: Jelly serum texture, Sprayable format, Hydrogel composition. Its shape, packaging and colors must stay exactly the same across all shots.
Keep the same person consistent across every shot; exactly one person, no duplicate people.
The person is NOT talking: mouth relaxed and mostly closed, no lip movement, no speaking, no lip-sync. AUDIO: ambient and diegetic sounds only (room tone, product handling, fabric, water); absolutely NO voice, NO speech, NO dialogue, NO narration, NO singing, and no spoken words in any language. Voiceover is added separately.
Do not render any on-screen text, captions, subtitles, letters, words or watermarks; clean footage with no text overlay.
character: American (Western), exceptionally attractive, flawless dewy skin, top viral beauty influencer and TikToker aesthetic, celebrity-tier face, model-tier, magnetic and highly photogenic, aspirational 'it-girl' look; product (keep identical in every shot): BIODANCE Collagen Peptides Jelly Serum Mist, a Face Mists, Jelly Serum Mist, Sprayable Hydrogel, in a Sprayable bottle, distinctive: Jelly serum texture, Sprayable format, Hydrogel composition; mood and tone: fresh, luminous, aspirational, chic; framing: vertical 9:16, subject very large — tight on the face, from the upper chest up so the face fills most of the frame (face beauty product); color grading matching this palette: soft pink, dewy white, warm beige, glassy clear; location: A chic, modern bathroom vanity with minimalist decor, perfect for an aspirational morning skincare routine; lighting: Soft, diffused morning natural light combined with a flattering front fill light to accentuate a flawless, dewy skin glow; mood: Fresh, radiant, and effortlessly trendy, capturing the aspirational 'clean girl' TikTok aesthetic; no on-screen text, captions, letters or watermarks
Shot 1: Close-Up — the creator, She gently presses and pats the essence into her skin with both hands, her expression shifting to pure delight as her face visibly plumps up.. Camera: Static hold.
Shot 2: Over-the-shoulder POV — the creator, Looking into her vanity mirror, she turns her head side to side, showing off the radiant, flawless glass-skin reflection catching the warm bathroom lights.. Camera: Slow pull-back.
Shot 3: Close-Up — the BIODANCE Collagen Peptides Jelly Serum Mist product in focus, She winks at the camera with a confident smile, holding the BIODANCE bottle right up to the lens and tapping the pink cap playfully with her perfectly manicured finger.. Camera: Whip pan.
