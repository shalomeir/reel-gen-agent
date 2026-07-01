"""Gemini 멀티모달로 비정형 속성을 묘사한다.

목소리 톤, 영상 느낌/무드, 자막 스타일, 후크, 내러티브를 구조화 출력(JSON)으로 받는다.
업로드/폴백 플러밍은 gemini_client에 모아 두고, 이 파일은 프롬프트와 결과 타입만 담당한다.
키가 없거나 호출이 끝까지 실패하면 빈 결과를 반환해 정형 계층만으로도 분석이 끝나게 한다.
"""

from __future__ import annotations

from . import gemini_client
from .profile import GeminiDescription

FALLBACK_FRAMES = gemini_client.FALLBACK_FRAMES

_BASE_PROMPT = """\
You are a short-form video analyst for a vertical product-ad generation harness.
Fill the structured schema, focusing on perceptual qualities a numeric pipeline cannot capture:
- voice: is there narration/dialogue? If so, describe the vocal tone and pace. If only BGM, present=false.
  Also set voice.on_camera=true only if the visible person is talking to the camera (mouth clearly
  moving in sync with the speech, a talking-head); set on_camera=false for off-screen voiceover over b-roll.
- music_dynamics: "build" if the audio energy clearly rises toward a payoff, else "flat".
- music_beat_synced: do the cuts land on musical beats, or follow meaning/action?
- subtitle: transcribe on-screen caption text, and describe font_style, color, position
  (top/center/bottom/mixed), density (keyword vs full_transcript), and any emoji used.
- visual_palette: dominant color mood words (e.g. "warm beige", "soft pink").
- visual_motion: still / gentle / dynamic.
- hook (first 3s): headline, product_line, bottom_caption, and the visual hook.
- tone: mood labels (e.g. fresh, clinical, sensorial, cinematic, ugc, authentic).
- narrative_arc: ordered beats (e.g. ["problem", "apply", "payoff"]).
- description: one vivid Korean paragraph describing the voice tone and overall feel of the video.

Write `description` in Korean. Keep other string fields concise.
"""

# 영상 경로용 / 프레임 폴백용 프롬프트. 폴백은 오디오가 없음을 모델에 알린다.
PROMPT_VIDEO = "Analyze this vertical short video.\n" + _BASE_PROMPT
PROMPT_FRAMES = (
    f"These are {FALLBACK_FRAMES} keyframes (no audio) sampled in order from a "
    "vertical skincare short video.\n"
    + _BASE_PROMPT
    + "\nAudio is unavailable here: set voice.present only if text/lips clearly imply speech, "
    "and leave music fields null."
)


def describe(
    path: str,
    duration_sec: float | None,
    api_key: str | None = None,
    model: str | None = None,
) -> GeminiDescription:
    """영상을 Gemini로 분석해 비정형 묘사를 반환한다.

    실패해도 예외 없이 빈 GeminiDescription을 낸다.
    """
    result = gemini_client.run_multimodal(
        path,
        duration_sec,
        schema=GeminiDescription,
        video_prompt=PROMPT_VIDEO,
        frames_prompt=PROMPT_FRAMES,
        api_key=api_key,
        model=model,
        log_prefix="gemini_describe",
    )
    return result if result is not None else GeminiDescription()
