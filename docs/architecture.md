# 아키텍처

`reel-gen-agent`는 분석과 생성을 분리해 두고, 둘을 안정적인 JSON 인터페이스로 잇는다.
레퍼런스 영상을 프로파일링하는 엔진이 생성된 영상도 채점한다. 그래서 둘 다 같은 잣대로
판단된다.

## 파이프라인

```
reference.mp4
   │  analyze
   ▼
VideoProfile / style_profile.json        (Stage 0, 구현됨)
   │  컷 리듬을 씨앗으로
   ▼
generation_input.json                    (Stage B 산출물)
   ▼  [gate: concept]
asset bible (character + product images)  (설계됨)
   ▼  [gate: asset_bible]
storyboard.json + panel stills            (설계됨)
   ▼  [gate: storyboard]
video (image-to-video per panel + ffmpeg) (설계됨)
   ▼  [gate: video]
Gate: profile(output) vs style_profile    (유사도 점수)
```

## 왜 나눴나

생성 백엔드(이미지 모델, 영상 모델)는 가장 바뀌기 쉬운 부분이다. 스키마를 고정해 두면
백엔드를 교체해도 한 단계만 건드리지 시스템 전체를 손대지 않는다. `style_profile.json`과
생성 스키마가 그 고정된 인터페이스다.

## 닫힌 루프

분석기는 레퍼런스에서 컷 수, 컷 길이, 내러티브 아크를 측정한다. 스토리보드 생성기는 그
숫자를 읽어 패널을 몇 개로 자르고 각 패널을 얼마나 길게 둘지 정한다. 빠른 컷 13개짜리
레퍼런스는 느린 컷 5개짜리와 다른 스토리보드 리듬을 만든다. 하드코딩된 규칙은 없다.
분석기는 Stage 0 프로파일러이자, 스토리보드 씨앗 공급자이자, 게이트 채점기다.

## 모듈

```
src/reel_gen_agent/
  analysis/        # 레퍼런스 영상 -> VideoProfile (구현됨)
    profile.py         # VideoProfile 스키마 (pydantic)
    media_probe.py     # ffprobe: 컨테이너 메타데이터
    cut_detector.py    # PySceneDetect: 컷 분포
    audio_features.py  # librosa: 오디오 다이내믹
    visual_features.py # OpenCV: 팔레트, 밝기
    gemini_describe.py # Gemini: 지각 필드
    list_writer.py     # 프로파일 -> 레퍼런스 카탈로그 항목
    analyze.py         # 오케스트레이터: analyze_video(path)
  generate/        # 생성 파이프라인 (설계됨; schema.py 있음)
    schema.py          # generation_input / asset bible / storyboard 스키마
  cli.py           # typer CLI
```

분석기는 [analysis.md](analysis.md), 생성 파이프라인은
[pipeline-design.md](pipeline-design.md)를 참고.
