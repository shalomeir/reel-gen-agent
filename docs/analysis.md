# 분석 계층

레퍼런스 숏폼 영상을 재사용 가능한 `VideoProfile`(JSON)로 바꾼다. 같은
`analyze_video(path)` 함수가 세 가지 호출자를 모두 처리한다.

- 레퍼런스 영상 -> `style_profile.json` (Stage 0)
- 다운로드한 URL -> 레퍼런스 카탈로그 항목
- 생성된 출력 -> 게이트 유사도 채점용 프로파일

## 두 계층, 하나의 프로파일

- **정형(로컬, 재현 가능):** 같은 입력은 늘 같은 숫자를 낸다. 게이트 유사도의 근거다.
  - `media_probe.py` (ffprobe): 해상도, fps, 길이, 종횡비
  - `cut_detector.py` (PySceneDetect): 컷 수, 평균/최소/최대 컷 길이, 모드
  - `audio_features.py` (librosa): BPM, 빌드 대 플랫 다이내믹, 인트로 무음
  - `visual_features.py` (OpenCV): 주요 팔레트(hex), 밝기, 대비
- **지각(Gemini 멀티모달):** 사람이 읽을 수 있는 설명과 카테고리 라벨.
  - `gemini_describe.py`: 보이스 톤, 느낌, 자막 스타일, 훅, 내러티브 아크

`analyze.py`가 둘을 하나의 프로파일로 합친다. 정형 측정값은 지각 계층이 덮어쓰지 않는다.

## Gemini 입력 선택

짧은 영상은 File API로 통째로 올려서 오디오까지 분석한다. 영상 스트림이 콘텐츠 필터에
걸리거나 길이가 60초를 넘으면, 분석기가 샘플링한 키프레임(오디오 없음)으로 폴백한다.
폴백은 자동이라 분석은 어떻든 끝까지 완료된다.

## 실행

```bash
reel-gen analyze video.mp4                         # JSON을 stdout으로
reel-gen analyze video.mp4 --out profiles/x.json   # 저장 + 출처 기록
reel-gen analyze video.mp4 --no-gemini             # 정형 계층만
```

## VideoProfile 필드

`container`, `cut`, `visual`, `subtitle`, `voice`, `music`, `hook`, `tone`,
`narrative_arc`, `description`, `source`. 기준은 `profile.py`의 pydantic 모델이다.

## 메모

- 분석기는 `GEMINI_API_KEY`만으로 돈다. 키가 없으면 정형 계층이 부분 프로파일을
  만들어 낸다.
- 컷 민감도는 파라미터다(PySceneDetect 임계값). 더 빠른 디졸브를 잡으려면 낮춘다.
  핵심은 컷 리듬이 상수가 아니라 데이터라는 점이다.
