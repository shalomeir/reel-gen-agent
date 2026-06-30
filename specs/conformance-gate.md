# Conformance 게이트: 결과물 무결성·적합성 검증 계약

상태: 확정. 이 문서는 생성된 영상이 "의도한 대로 기술적으로 온전히 만들어졌나"를 어떻게
pass/fail로 판정하는지를 고정한다. 구현이 따라야 하는 체크 카탈로그, 3상태 모델, 임계값,
스키마 경계, 레퍼런스 통과 규칙, 완료 기준을 못박는다. 코드와 어긋나면 이 문서가 이긴다.

## rubric과의 관계

평가 축이 둘이다.

- **드라이버 Rubric**([rubric.md](rubric.md)): "콘텐츠로서 먹히나". 정성, 0~100 점수, 소프트.
- **Conformance 게이트**(이 문서): "의도대로 온전히 만들어졌나". 객관, pass/fail, 하드.

순서가 있다. **Conformance가 먼저다.** 깨지거나 빠진 영상을 정성 채점하는 건 의미가 없다.
생성 그래프의 최종 단계에서 Conformance가 fail이면 Rubric 채점으로 가지 않고 막거나, 약한
샷을 재생성한다. 둘 다 통과해야 좋은 생성물이다.

## 3상태 체크 모델

게이트는 여러 개의 작은 체크로 이뤄진다. 각 체크는 세 상태 중 하나다.

- `pass`: 기준을 만족.
- `fail`: 기준 위반.
- `skip`: 평가에 필요한 기대 스펙이 없어 건너뜀(예: 레퍼런스에 템플릿이 없음).

**전체 passed = fail이 0개**(skip은 통과로 친다). 깨진 파일이나 디코드 실패는 예외로 던지지
않고 해당 체크 `fail`로 환원해 게이트 자체가 죽지 않게 한다.

체크는 두 부류다.

- **intrinsic(내재적)**: 템플릿 없이도 성립하는 기술 무결성. 레퍼런스에서도 돈다.
- **template-derived(템플릿 파생)**: 기대 스펙(템플릿/스토리보드/매니페스트)이 있어야 성립.
  스펙이 없으면 `skip`.

## 레퍼런스가 모두 통과하는 이유

레퍼런스 영상은 우리 그래프를 거치지 않아 템플릿도 매니페스트도 없다. `verify_conformance`를
기대 스펙 없이 호출하면 intrinsic 체크만 돌고 나머지는 전부 `skip`이다. 잘 만든 레퍼런스는
intrinsic(유효한 mp4, 9:16, 오디오 있음, 블랙/프리즈 아님, 볼륨 정상 등)을 만족하므로
`fail`이 0개라 PASS다. VLM 지각 체크는 "명백한 결함만 flag"하도록 보수적으로 프롬프트해,
정상 영상이 거짓 fail로 막히지 않게 한다.

## 진입점과 데이터 흐름

```
verify_conformance(path, input=None, storyboard=None, manifest=None, config=None) -> ConformanceReport
  A. 미디어 무결성        항상 (intrinsic)
  B. 템플릿 적합성        input 있으면
  C. 노드그래프·머지 무결성 manifest(+storyboard) 있으면
  D. 레이어 교차 일관성    storyboard 있으면 (final 재분석)
  E. 지각 결함(OCR/VLM)   항상 일부(intrinsic) + input/storyboard 있으면 일부(template-derived)
```

레퍼런스: `verify_conformance(ref.mp4)` -> A + E의 intrinsic만 -> PASS.
생성물: 넷 다 넘김 -> 전부 평가.

## 체크 카탈로그

각 체크는 `code`, `category`, `intrinsic`, 통과 조건을 가진다. `code`는 `범주.이름` 형식이다.

### A. 미디어 무결성 (category: media, intrinsic)

| code | 통과 조건 |
|---|---|
| `media.file_valid` | 파일 존재, 0바이트 아님, ffprobe 파싱됨 |
| `media.container_complete` | moov atom 존재, 잘리지 않음(끝 타임스탬프 ≈ 길이) |
| `media.video_decodable` | 비디오 스트림 1개, 끝까지 디코드(손상 프레임 없음) |
| `media.audio_present` | 오디오 스트림 존재(음악/보이스 기대 시 필수) |
| `media.aspect_ratio` | `config.expected_aspect_ratio`(기본 9:16)와 일치 |
| `media.resolution_min` | 가로 폭 ≥ `config.min_width` |
| `media.duration_positive` | 길이 > 0 |
| `media.not_black` | 샘플 프레임의 큰 비율이 near-black이 아님(평균 luma 임계 초과 프레임 존재) |
| `media.not_frozen` | 인접 샘플 프레임 평균 차이가 임계 이상(정지영상 아님) |
| `media.audio_not_silent` | 오디오가 있으면 통합 RMS가 바닥 위(전체 무음 아님) |

### B. 템플릿 적합성 (category: template, template-derived)

`GenerationInput`(input)이 있을 때만. 레퍼런스는 전부 skip.

| code | 통과 조건 |
|---|---|
| `template.duration_match` | 실제 길이가 `meta.duration_sec` ± 허용오차 이내 |
| `template.aspect_match` | 실제 종횡비 == `meta.aspect_ratio` |
| `template.fps_match` | 실제 fps == `meta.fps` ± `config.fps_tolerance` |
| `template.duration_within_platform` | 길이가 `meta.platform`의 권장 상한 이내 |
| `template.subtitle_present` | `subtitle.density != none`이면 화면에 자막이 존재 |
| `template.watermark_present` | `input.watermark`가 있으면 워터마크가 적용됨 |
| `template.voice_mode` | `voice.enabled`면 음성 트랙/스피치 존재, 아니면 music bed |
| `template.music_present` | `music`이 지정됐으면 오디오 트랙 존재 |

### C. 노드그래프·머지 무결성 (category: nodegraph / merge, template-derived)

`RunManifest`(+ `Storyboard`)가 있을 때만. 생성 그래프가 매니페스트를 낳기 전에는 합성
데이터로 단위 테스트하고, 실제 산출물 연결은 generate 구현 시 한다.

| code | 통과 조건 |
|---|---|
| `nodegraph.all_nodes_done` | 모든 노드 status == done, 에러 노드 없음 |
| `nodegraph.artifacts_exist` | 각 노드가 선언한 산출물 파일이 실제 존재하고 0바이트 아님 |
| `nodegraph.input_schema_valid` | generation_input JSON이 `GenerationInput` 스키마 통과 |
| `nodegraph.storyboard_schema_valid` | storyboard JSON이 `Storyboard` 스키마 통과 |
| `nodegraph.panel_stills_exist` | 패널마다 still 이미지가 존재 |
| `nodegraph.panel_clips_exist` | 패널마다 영상 클립이 존재(영상 단계가 돈 경우) |
| `nodegraph.asset_lock_referenced` | `subject_lock`/`product_lock` 패널이 에셋 이미지를 참조 |
| `merge.segment_count` | concat된 세그먼트 수 == 패널 수(드롭/중복 없음) |
| `merge.timeline_contiguous` | 패널 타임라인에 갭/오버랩 없음(`t_end[i] ≈ t_start[i+1]`) |
| `merge.duration_sum` | 패널 길이 합 ≈ final 영상 길이 |
| `merge.av_sync` | 오디오 길이 ≈ 비디오 길이(mux 드리프트 없음) |

### D. 레이어 교차 일관성 (category: cross, template-derived)

`Storyboard`가 있을 때만. final 영상을 분석기로 재프로파일링해 비교한다.

| code | 통과 조건 |
|---|---|
| `cross.cut_count_match` | 재분석 컷 수가 스토리보드 패널 수와 근사(style_profile 시딩이 반영됨) |

자막 텍스트가 스토리보드와 맞는지는 OCR/VLM이라 E의 `perceptual.subtitle_text_match`로 둔다.

### E. 지각 결함 (category: perceptual, OCR/VLM)

명백한 결함만 binary로 잡는다. 정성 점수가 아니라 "깨졌나/잘렸나/어색한가"의 pass/fail이다.
엔진은 Gemini 멀티모달이다(텍스트 읽기 + 위치/효과/전환 판정을 한 structured 호출로). 키가
없으면 VLM 전용 체크는 `skip`(게이트를 막지 않음). 볼륨은 VLM이 아니라 결정론이다.

| code | intrinsic | 통과 조건 |
|---|---|---|
| `perceptual.volume_loudness` | O | 통합 라우드니스(LUFS)가 `config.lufs_min`~`lufs_max` 범위 내 |
| `perceptual.volume_no_clipping` | O | 트루 피크가 `config.true_peak_max_dbtp` 이하(클리핑 없음) |
| `perceptual.cut_no_broken_frames` | O | 컷 경계에 깨진 블랙/플리커 프레임 없음(결정론, 프레임 샘플) |
| `perceptual.cut_transition_clean` | O | (VLM) 컷 전환이 매끄럽고 의도적, 끊김/깨진 프레임 없음 |
| `perceptual.subtitle_in_safe_zone` | O | (VLM) 자막이 화면 밖으로 잘리거나 플랫폼 UI 영역을 침범하지 않음 |
| `perceptual.subtitle_not_awkward` | O | (VLM) 자막이 피사체 핵심을 가리거나 어색하게 배치되지 않음 |
| `perceptual.subtitle_legible` | O | (VLM) 외곽선/대비가 충분해 읽힘, 컬러 이모지가 두부로 깨지지 않음 |
| `perceptual.product_fit_purpose` | O | (VLM) 제품이 영상 목적에 맞게 표현됨(잘 보이고 왜곡 없음). 제품 미등장이면 skip |
| `perceptual.model_appeal_fit` | O | (VLM) 등장인물이 이 영상 목적을 전달할 매력을 가짐. 인물 미등장이면 skip |
| `perceptual.subtitle_text_match` | X | (VLM/OCR) 읽은 자막이 storyboard `subtitle_text`와 일치(생성물만) |
| `perceptual.transition_as_specified` | X | (VLM) storyboard가 지정한 전환이 실제로 적용됨(생성물만) |

## 설정 (ConformanceConfig)

임계값은 코드에 박지 않고 주입한다. 기본값(튜닝 가능):

| 파라미터 | 기본값 | 뜻 |
|---|---|---|
| `expected_aspect_ratio` | `"9:16"` | 세로 종횡비 |
| `min_width` | 480 | 최소 가로 폭(실측 레퍼런스 576-wide 통과) |
| `duration_tolerance_sec` | 0.75 | 길이 일치 절대 허용오차 |
| `duration_tolerance_ratio` | 0.10 | 길이 일치 비율 허용오차(둘 중 큰 쪽 적용) |
| `fps_tolerance` | 1.0 | fps 허용오차 |
| `platform_max_sec` | `{tiktok:600, reels:90, shorts:60}` | 플랫폼별 길이 상한 |
| `black_luma_max` | 12.0 | near-black 판정 평균 luma 상한(0~255) |
| `freeze_min_diff` | 2.0 | 정지 아님 판정 인접 프레임 최소 평균차 |
| `silence_floor_dbfs` | -60.0 | 전체 무음 판정 피크 바닥(dBFS) |
| `lufs_min` / `lufs_max` | -30.0 / -5.0 | 통합 라우드니스 허용 범위(LUFS, BS.1770 게이팅). 마스터링 타깃이 아니라 극단만 거르는 새너티 폭. 가장 조용한 실측 레퍼런스(약 -26)도 통과. 생성물엔 config로 더 타이트하게 |
| `true_peak_max_dbtp` | 0.0 | 클리핑 판정 상한. 샘플 피크 기준이라 풀스케일(0 dBFS) 도달만 잡는다 |
| `cut_count_tolerance` | 2 | 컷 수 일치 허용 편차 |
| `sample_frames` | 16 | 결정론 프레임 샘플 수 |

## 스키마 경계

`generate/conformance.py`에 정의한다. 생성 그래프의 게이트가 `ConformanceReport`를 소비한다.

- `ConformanceCheck` — `code`, `category`(media/template/nodegraph/merge/cross/perceptual),
  `intrinsic`(bool), `status`(pass/fail/skip), `expected`, `actual`, `detail`(한국어).
- `ConformanceReport` — `checks`(목록), `passed`, `counts`(pass/fail/skip), `source`.
- `ConformanceConfig` — 위 임계값들.

run manifest 계약은 `generate/schema.py`에 둔다(생성 그래프가 기록).

- `NodeRun` — `name`(concept/asset_bible/storyboard/video/subtitles/music/assembly),
  `status`(done/error/skipped), `artifacts`(산출물 경로 목록), `error`.
- `RunManifest` — `run_id`, `input_path`, `storyboard_path`, `final_video`,
  `panel_segments`(concat 순서대로의 클립 경로), `nodes`(NodeRun 목록).

## OCR/VLM 레이어

엔진은 Gemini 멀티모달이며 `analysis/gemini_client.run_multimodal`을 재사용한다. 한 번의
structured 호출로 다음을 받는다: 화면 자막 텍스트, 자막 위치(top/center/bottom과 세이프존
침범 여부), 자막 가독성/효과 깨짐 여부, 컷 전환의 매끄러움, 끊김/깨진 프레임 여부. 각 항목은
binary 결함 플래그 + 한국어 근거다. 모델은 "명백한 결함만 보고하고 애매하면 통과"로
프롬프트한다. 정밀 박스 좌표가 필요해지면 pytesseract를 옵션 폴백으로 둔다(시스템 의존성이라
기본 경로 아님).

## 모듈 레이아웃

```
src/reel_gen_agent/
  generate/
    schema.py        # + NodeRun, RunManifest
    conformance.py   # ConformanceConfig/Check/Report + verify_conformance + 각 체크
  analysis/
    frame_sampler.py # 블랙/프리즈 판정용 균등 프레임 샘플(분석은 generate를 모름)
    loudness.py      # 통합 라우드니스(LUFS)와 트루 피크 측정
```

intrinsic 미디어/볼륨 체크는 analysis 헬퍼를 재사용한다. generate -> analysis 의존만 두고
analysis -> generate 의존은 만들지 않는다.

## CLI와 게이트 동작

```
reel-gen verify <video> [--input generation_input.json] [--storyboard storyboard.json]
                        [--manifest run.json] [--out evals/conformance/x.json] [--no-vlm]
```

- fail이 하나라도 있으면 **exit code != 0**(진짜 게이트).
- `--no-vlm`은 VLM 체크를 전부 skip(결정론 체크만).
- 생성 그래프의 최종 게이트는 이 `passed`를 통과 신호로 쓴다. fail이면 Rubric 채점으로
  가지 않고, 결함 카테고리로 해당 샷 재생성을 트리거한다.
- 레퍼런스 일괄 검증 결과는 `evals/conformance/`에 저장한다. `.gitignore`를 `evals/` 전체로
  넓힌다.

## 지금 구현 vs 계약만

- **지금 구현 + 검증**: A(미디어 무결성), B(템플릿 적합성), E(지각 결함: 볼륨은 결정론,
  자막/전환은 VLM), 스키마 검증, D의 컷 수 비교. 레퍼런스 5편으로 PASS를 증명하고, 손수
  만든 샘플 template로 B를 테스트한다.
- **결정론 함수로 구현 + 합성 데이터 단위 테스트**: C(노드/머지 무결성). `RunManifest`와
  합성 storyboard로 단언한다. 실제 generate 산출물 연결은 generate 구현 시.
- **계약만**: E의 자막 텍스트 매칭(`perceptual.subtitle_text_match`)은 VLM 자막 읽기로
  구현하되, 정밀 좌표 OCR(pytesseract)은 폴백으로 남긴다.

## 완료 기준

- `generate/conformance.py`가 위 카탈로그와 3상태 모델, 설정 주입을 구현한다.
- 결정론 체크(A, B, 볼륨, 머지, 스키마)가 단위 테스트로 덮인다. VLM 호출은 목으로 막는다.
- `reel-gen verify`가 동작하고 fail 시 exit code != 0.
- 레퍼런스 영상들이 모두 PASS하고 결과가 `evals/conformance/`에 저장된다. `evals/`는 gitignore.
- 깨진/블랙/무음 합성 클립에 대해 해당 체크가 fail로 나온다.
- 임계값을 바꾸면 판정이 따라 바뀐다(하드코딩 금지).
