"""fal Kling O3 백엔드 + VIDEO_MODEL_PRIORITY lane 선택 + 백엔드 디스패치 검증.

fal API는 호출하지 않는다(스키마 매핑·선택 로직만 단위 검증).
"""

from __future__ import annotations

from reel_gen_agent.generate.backends.kling import (
    _MAX_PROMPT,
    FalVideoBackend,
    _build_arguments,
    _fit_prompt,
)
from reel_gen_agent.generate.capability import capability_for
from reel_gen_agent.generate.materials import _video_backend
from reel_gen_agent.generate.production_plan import _select_video_model
from reel_gen_agent.generate.schema import ProductionPlan

_I2V = "fal-ai/kling-video/o3/standard/image-to-video"
_R2V = "fal-ai/kling-video/o3/standard/reference-to-video"


# --- fal 인자 매핑 ---------------------------------------------------------------


def test_i2v_arguments_use_image_url():
    args = _build_arguments(_I2V, "start://u", [], 6.0, "hello", generate_audio=False)
    assert args["image_url"] == "start://u"
    assert "start_image_url" not in args and "image_urls" not in args
    assert args["duration"] == "6"
    assert args["prompt"] == "hello"


def test_r2v_arguments_use_start_and_reference_images():
    args = _build_arguments(
        _R2V, "start://u", ["ref://c", "ref://p"], 8.0, "hi", generate_audio=True
    )
    assert args["start_image_url"] == "start://u"
    assert args["image_urls"] == ["ref://c", "ref://p"]
    assert args["aspect_ratio"] == "9:16"
    assert args["generate_audio"] is True
    assert "image_url" not in args


def test_duration_clamped_to_kling_range():
    assert _build_arguments(_I2V, "u", [], 1.0, "", False)["duration"] == "3"  # 하한 3
    assert _build_arguments(_I2V, "u", [], 40.0, "", False)["duration"] == "15"  # 상한 15


def test_prompt_capped_to_kling_limit_keeping_shots():
    # Kling은 prompt 2500자 초과를 422로 거절한다 -> 한도 안으로 줄이되 샷 리스트는 보존해야 한다.
    head = "STYLE " + "x" * 3000  # 아주 긴 스타일 서술(앞부분)
    prompt = head + "\nShot 1: macro CU of the product.\nShot 2: medium, the creator."
    fit = _fit_prompt(prompt)
    assert len(fit) <= _MAX_PROMPT
    assert "Shot 1:" in fit and "Shot 2:" in fit  # 샷 리스트(끝)는 안 잘린다
    # 실제 인자에도 반영된다.
    args = _build_arguments(_I2V, "u", [], 6.0, prompt, False)
    assert len(args["prompt"]) <= _MAX_PROMPT


def test_short_prompt_unchanged():
    assert _fit_prompt("short prompt") == "short prompt"


# --- 우선순위 lane 선택 ----------------------------------------------------------


def test_priority_picks_fal_when_fal_key_present():
    env = {
        "VIDEO_MODEL_PRIORITY": f"fal:{_I2V},vertex-veo:veo-3.1-fast-generate-001",
        "FAL_KEY": "k",
    }
    assert _select_video_model(env) == _I2V


def test_priority_skips_lane_without_credentials():
    # fal 키가 없으면 fal 후보를 건너뛰고 자격 있는 vertex를 고른다.
    env = {
        "VIDEO_MODEL_PRIORITY": f"fal:{_I2V},vertex-veo:veo-3.1-fast-generate-001",
        "GOOGLE_CLOUD_PROJECT": "proj",
    }
    assert _select_video_model(env) == "veo-3.1-fast-generate-001"


def test_priority_none_when_no_credentials():
    assert _select_video_model({"VIDEO_MODEL_PRIORITY": f"fal:{_I2V}"}) is None


# --- capability + 디스패치 -------------------------------------------------------


def test_capability_marks_fal_lane_for_kling_ids():
    cap = capability_for(_I2V)
    assert cap.lane == "fal"
    assert cap.integrated_voice is True  # Kling은 네이티브 발화 가능
    assert cap.max_clip_sec == 10.0


def test_video_backend_dispatches_fal_for_kling():
    be = _video_backend(ProductionPlan(video_model=_I2V))
    assert isinstance(be, FalVideoBackend)
    assert be.model == _I2V


def test_video_backend_none_for_ken_burns():
    assert _video_backend(ProductionPlan(video_model="ken_burns")) is None
