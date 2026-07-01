# 최종 리포트 — want-this-effortless-morning-glow-20260701-235953

## 유저 입력
- 목적: 제품: glow serum. 목적: 아침 스킨케어 루틴 숏폼 광고, 촉촉한 광채 강조. reference: reference_video/사전과제_reference1.mp4
- 제품: glow
- 레퍼런스: reference_video/사전과제_reference1.mp4

## 캐릭터
- age: early 20s
- gender: female
- look: Black/African descent, celebrity-level supermodel-tier gorgeous, stunning head-turning beauty with a flawless deep skin tone and a natural dewy glow. She has short, dark, curly hair pulled back and is wearing a light pink t-shirt.

## 스타일
- tone: radiant, effortless, fresh, premium
- pacing: mixed
- motion: gentle
- palette: warm morning gold, soft pastel pink, deep mahogany, dewy translucent

## 훅
- type: H2
- headline: Want this effortless morning glow?
- bottom_caption: morning skincare routine ✨
- visual: Extreme close-up of her flawless, deeply melanated skin catching the natural morning sunlight. She tilts her cheek to show off the glass-like reflection, smiling effortlessly in her light pink t-shirt with her short curly hair pulled neatly back.

## 스토리보드
- `00:00` [hook] — She tilts her cheek gently to catch the bright morning sunlight, revealing a flawless, glass-like reflection on her deeply melanated skin. 자막:"Want this effortless morning glow?"
- `00:01` [establish] — Standing in a bright, minimalist bathroom in her light pink t-shirt, she smiles confidently and holds up the glow serum bottle to the camera. 자막:"morning skincare routine ✨"
- `00:02` [demonstrate texture] — Her hands vigorously shake the clear bottle, showing the thick jelly texture inside instantly transforming into a fluid liquid. 자막:"Jelly-to-mist magic"
- `00:03` [demonstrate usage] — She closes her eyes and presses the nozzle, spraying a fine, even mist of the serum directly across her face. 자막:"Instant hydration"
- `00:04` [action detail] — Her fingertips gently and rhythmically pat the damp mist into her cheeks, blending it seamlessly into her skin. 자막:"Pat gently"
- `00:05` [reaction] — She opens her eyes and looks directly into the lens, her expression instantly refreshed as her skin looks visibly plumper. 자막:"So refreshing!"
- `00:07` [proof/result] — She slowly turns her head side-to-side, showcasing the ultimate dewy, radiant finish on her cheekbones. 자막:"Dewy perfection"
- `00:08` [product hero] — The glow serum bottle rests on the clean white bathroom sink; focus pulls sharply from her smiling in the background to the bottle in the foreground. 자막:"The ultimate glow serum"
- `00:09` [payoff/cta] — She holds the bottle next to her glowing face, gives a confident wink, and playfully points down toward the bottom of the screen. 자막:"Get yours now! 👇"

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
| 영상 클립 (9개 클립) | veo-3.1-fast-generate-001 | 초 | 10.7 | $0.150 | $1.605 |
| BGM | lyria-3-pro-preview | 클립 | 1 | $0.040 | $0.040 |
| 나레이션 (대사 글자수 기준) | eleven_v3 | 1k자 | 0.102 | $0.180 | $0.018 |
| 품질 평가 (conformance + rubric) | gemini-2.5-flash | 호출 | 2 | $0.020 | $0.040 |
| **합계** |  |  |  |  | **$1.943** |

- 단가는 공개 근사치(기준일 2026-07-01)이며 실제 청구와 다를 수 있음
- ken_burns/합성 BGM 등 로컬 폴백은 $0으로 계산
- 기획·카피 텍스트 LLM(컨셉/훅/스토리보드/대사)은 별도 planning 단계라 미포함
- SFX는 플랜이 켰을 때만 집계(컷 sfx 큐 기준). Kling O3는 배선되면 자동 반영
- 이미지 수는 스틸 있는 패널 기준 추정(사용자 제공 스틸이 섞일 수 있음)

## BGM
- 방식 gen, 모델 lyria-3-pro-preview
- 음악: 무드 Radiant, effortless, and warm, 장르 Clean modern instrumental Afro-R&B and chill Afrobeat, relaxed but driving syncopated groove, 템포 136 bpm, 악기 Warm rolling sub bass, syncopated wooden percussion with crisp rimshots and shakers, soft Rhodes piano chords, gentle atmospheric synth pads, clean muted guitar plucks, 존재감 background

## 평가
- conformance: {'checks': [{'code': 'media.file_valid', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '파일 유효, ffprobe 파싱됨'}, {'code': 'media.container_complete', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '컨테이너 길이 정보 존재(잘림 없음)'}, {'code': 'media.video_decodable', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': '16 frames', 'detail': '프레임 디코드됨'}, {'code': 'media.audio_present', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '오디오 스트림 존재'}, {'code': 'media.aspect_ratio', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': '9:16', 'actual': '9:16', 'detail': None}, {'code': 'media.duration_positive', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': '10.833', 'detail': None}, {'code': 'media.resolution_min', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': '>= 480px wide', 'actual': '1080x1920', 'detail': None}, {'code': 'media.not_black', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'black ratio 0.00', 'detail': '정상 밝기 프레임 존재'}, {'code': 'media.not_frozen', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'adjacent diff 47.26', 'detail': '프레임 변화 있음'}, {'code': 'media.audio_not_silent', 'category': 'media', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': 'peak -2.08 dBFS', 'detail': '오디오 신호 존재'}, {'code': 'perceptual.volume_loudness', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': '-21.0 ~ -9.0 LUFS', 'actual': '-18.97 LUFS', 'detail': None}, {'code': 'perceptual.volume_no_clipping', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': '<= 0.0 dBTP', 'actual': '-2.08 dBFS', 'detail': None}, {'code': 'perceptual.cut_no_broken_frames', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '깨진 프레임 없음'}, {'code': 'perceptual.cut_transition_clean', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '영상이 깔끔합니다.'}, {'code': 'perceptual.subtitle_in_safe_zone', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.subtitle_not_awkward', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.subtitle_legible', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': None}, {'code': 'perceptual.product_fit_purpose', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '제품이 목적에 맞게 표현됨'}, {'code': 'perceptual.model_appeal_fit', 'category': 'perceptual', 'intrinsic': True, 'status': 'pass', 'expected': None, 'actual': None, 'detail': '등장인물이 목적 전달에 적절'}, {'code': 'perceptual.subtitle_text_match', 'category': 'perceptual', 'intrinsic': False, 'status': 'skip', 'expected': None, 'actual': None, 'detail': '기대 자막 없음(레퍼런스/무자막)'}, {'code': 'perceptual.transition_as_specified', 'category': 'perceptual', 'intrinsic': False, 'status': 'skip', 'expected': None, 'actual': None, 'detail': '스토리보드 전환 타입 필드 추후'}], 'passed': True, 'counts': {'pass': 19, 'fail': 0, 'skip': 2}, 'source': {'path': 'outputs/want-this-effortless-morning-glow-20260701-235953/final.mp4', 'url': None, 'extractor_id': None}}
- rubric: {'dimensions': [{'code': 'D1', 'key': 'hook_strength', 'name': 'Hook 강도(첫 1~3초)', 'weight': 0.2, 'role': 'gate', 'score': 5, 'normalized': 1.0, 'rationale': "첫 1초부터 윤기나는 피부를 보여주며 '이런 광채를 원하세요?'라는 질문으로 즉시 시청자의 시선을 끈다."}, {'code': 'D2', 'key': 'watch_completion', 'name': '시청 완결 설계', 'weight': 0.18, 'role': 'gate', 'score': 5, 'normalized': 1.0, 'rationale': '빠른 전환과 제품 사용의 전 과정을 보여주며 시청자의 궁금증을 자극하고 끝까지 집중하게 만든다.'}, {'code': 'D3', 'key': 'content_value', 'name': '콘텐츠 가치', 'weight': 0.15, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '제품 사용법을 간결하게 시연하고 즉각적인 피부 변화를 보여주어 정보 가치가 높다.'}, {'code': 'D4', 'key': 'brand_integration', 'name': '브랜드 통합 자연스러움', 'weight': 0.14, 'role': 'additive', 'score': 5, 'normalized': 1.0, 'rationale': "영상 초반에 제시된 '광채'에 대한 해결책으로 제품이 자연스럽게 소개되어 광고처럼 느껴지지 않는다."}, {'code': 'D5', 'key': 'call_to_action', 'name': '행동 유발 설계', 'weight': 0.14, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '명확한 구매 유도 문구와 손가락 제스처로 행동을 촉구하지만, 공유나 저장 유도 요소는 부족하다.'}, {'code': 'D6', 'key': 'platform_native', 'name': '플랫폼 네이티브성', 'weight': 0.09, 'role': 'additive', 'score': 5, 'normalized': 1.0, 'rationale': '세로 영상 포맷, 텍스트 오버레이, 빠른 편집 등 숏폼 플랫폼의 특징을 잘 활용했다.'}, {'code': 'D7', 'key': 'trust_authenticity', 'name': '신뢰·진정성', 'weight': 0.1, 'role': 'additive', 'score': 4, 'normalized': 0.75, 'rationale': '과장되지 않은 자연스러운 피부 표현과 제품 사용 후 즉각적인 효과를 보여주어 신뢰성이 높다.'}], 'gate_coefficient': 1.0, 'additive_core': 0.8427, 'gated_score': 84.27, 'flat_score': 90.25, 'gate_passed': True, 'passed': True, 'summary': '이 영상은 아침 스킨케어 루틴을 통해 쉽고 자연스러운 광채 피부를 연출하는 미스트 제품 광고입니다.', 'expected_effect': "이 영상은 피부 광채에 관심 있는 젊은층 시청자들을 즉시 사로잡을 것입니다. 제품의 직관적인 효과와 매력적인 비주얼 덕분에 '스킨케어 팁' 또는 '메이크업 루틴' 관련 콘텐츠를 찾는 사용자들 사이에서 높은 시청 완료율과 공유/저장으로 이어질 잠재력이 큽니다. 짧고 간결한 형식으로 인해 뷰티 제품에 대한 인지도를 높이고 직접적인 구매 전환율을 유도하는 데 효과적일 것입니다.", 'source': {'path': 'outputs/want-this-effortless-morning-glow-20260701-235953/final.mp4', 'url': None, 'extractor_id': None}, 'scored': True}

## verify 교정(repair)
- 되돌린 횟수: 0
- 미해결 fail: 없음

## 바이럴 예측
(미작성)

## 노드별 프롬프트
### visuals
[segment 0] A single vertical 9:16 clip that moves through 6 shots played one after another over time (an edited sequence with varied pacing (a mix of longer holds and quicker cuts)).
Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, minimal, graceful subject motion — not busy or energetic, even though cuts are quick.
Keep the SAME product identical in every shot — the product is: glow, a serum mist, jelly-to-mist, in a clear pink spray bottle with a white pump, pink, white, clear tones, distinctive: clear pink bottle, white spray pump mechanism, visible jelly texture inside the bottle. Its shape, packaging and colors must stay exactly the same across all shots.
Keep the same person consistent across every shot; exactly one person, no duplicate people.
The person is NOT talking: mouth relaxed and mostly closed, no lip movement, no speaking, no lip-sync. AUDIO: ambient and diegetic sounds only (room tone, product handling, fabric, water); absolutely NO voice, NO speech, NO dialogue, NO narration, NO singing, and no spoken words in any language. Voiceover is added separately.
Do not render any on-screen text, captions, subtitles, letters, words or watermarks; clean footage with no text overlay.
character: Black/African descent, celebrity-level supermodel-tier gorgeous, stunning head-turning beauty with a flawless deep skin tone and a natural dewy glow. She has short, dark, curly hair pulled back and is wearing a light pink t-shirt.; product (keep identical in every shot): glow, a serum mist, jelly-to-mist, in a clear pink spray bottle with a white pump, pink, white, clear tones, distinctive: clear pink bottle, white spray pump mechanism, visible jelly texture inside the bottle; mood and tone: fresh, radiant, effortless, luminous; framing: vertical 9:16, subject large — upper body only by default; color grading matching this palette: light pink, rich mahogany, golden glow, soft morning white; location: A bright, modern bathroom with a clean, minimalist aesthetic and light-colored tones to contrast with her pink t-shirt; lighting: Soft, natural morning sunlight combined with diffused front lighting to beautifully accentuate the dewy glow on her deep skin tone; mood: Fresh, radiant, and effortlessly luxurious, capturing an uplifting morning energy; no on-screen text, captions, letters or watermarks
Shot 1: Extreme close-up — the creator, Extreme close-up of her flawless, deeply melanated skin catching the natural morning sunlight. She tilts her cheek to show off the glass-like reflection, smiling effortlessly in her light pink t-shirt with her short curly hair pulled neatly back.. Camera: Slow push-in.
Shot 2: Medium shot — the glow product in focus, Standing in a bright, minimalist bathroom in her light pink t-shirt, she smiles confidently and holds up the glow serum bottle to the camera.. Camera: Handheld slight orbit.
Shot 3: Macro detail — the glow product in focus, Her hands vigorously shake the clear bottle, showing the thick jelly texture inside instantly transforming into a fluid liquid.. Camera: Locked off.
Shot 4: Close-up — the glow product in focus, She closes her eyes and presses the nozzle, spraying a fine, even mist of the serum directly across her face.. Camera: Slow push-in.
Shot 5: Hands detail — the creator, Her fingertips gently and rhythmically pat the damp mist into her cheeks, blending it seamlessly into her skin.. Camera: Static.
Shot 6: Medium close-up — the creator, She opens her eyes and looks directly into the lens, her expression instantly refreshed as her skin looks visibly plumper.. Camera: Quick whip-pan.

[segment 1] A single vertical 9:16 clip that moves through 3 shots played one after another over time (an edited sequence with varied pacing (a mix of longer holds and quicker cuts)).
Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, minimal, graceful subject motion — not busy or energetic, even though cuts are quick.
Keep the SAME product identical in every shot — the product is: glow, a serum mist, jelly-to-mist, in a clear pink spray bottle with a white pump, pink, white, clear tones, distinctive: clear pink bottle, white spray pump mechanism, visible jelly texture inside the bottle. Its shape, packaging and colors must stay exactly the same across all shots.
Keep the same person consistent across every shot; exactly one person, no duplicate people.
The person is NOT talking: mouth relaxed and mostly closed, no lip movement, no speaking, no lip-sync. AUDIO: ambient and diegetic sounds only (room tone, product handling, fabric, water); absolutely NO voice, NO speech, NO dialogue, NO narration, NO singing, and no spoken words in any language. Voiceover is added separately.
Do not render any on-screen text, captions, subtitles, letters, words or watermarks; clean footage with no text overlay.
character: Black/African descent, celebrity-level supermodel-tier gorgeous, stunning head-turning beauty with a flawless deep skin tone and a natural dewy glow. She has short, dark, curly hair pulled back and is wearing a light pink t-shirt.; product (keep identical in every shot): glow, a serum mist, jelly-to-mist, in a clear pink spray bottle with a white pump, pink, white, clear tones, distinctive: clear pink bottle, white spray pump mechanism, visible jelly texture inside the bottle; mood and tone: fresh, radiant, effortless, luminous; framing: vertical 9:16, subject large — upper body only by default; color grading matching this palette: light pink, rich mahogany, golden glow, soft morning white; location: A bright, modern bathroom with a clean, minimalist aesthetic and light-colored tones to contrast with her pink t-shirt; lighting: Soft, natural morning sunlight combined with diffused front lighting to beautifully accentuate the dewy glow on her deep skin tone; mood: Fresh, radiant, and effortlessly luxurious, capturing an uplifting morning energy; no on-screen text, captions, letters or watermarks
Shot 1: Extreme close-up — the creator, She slowly turns her head side-to-side, showcasing the ultimate dewy, radiant finish on her cheekbones.. Camera: Slight pan.
Shot 2: Close-up — the glow product in focus, The glow serum bottle rests on the clean white bathroom sink; focus pulls sharply from her smiling in the background to the bottle in the foreground.. Camera: Rack focus.
Shot 3: Medium shot — the glow product in focus, She holds the bottle next to her glowing face, gives a confident wink, and playfully points down toward the bottom of the screen.. Camera: Static.
