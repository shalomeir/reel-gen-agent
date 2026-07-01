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
    args = _build_arguments(_I2V, "start://u", 6.0, "hello", generate_audio=False)
    assert args["image_url"] == "start://u"
    assert "start_image_url" not in args and "image_urls" not in args and "elements" not in args
    assert args["duration"] == "6"
    assert args["prompt"] == "hello"
    # generate_audio는 항상 명시한다(빼면 Kling 기본이 배경음악을 깐다). 발화 아니면 False.
    assert args["generate_audio"] is False


def test_r2v_character_and_product_go_to_elements():
    # 캐릭터·제품 정체성은 image_urls가 아니라 elements(frontal_image_url)로 넣는다.
    args = _build_arguments(
        _R2V, "start://u", 8.0, "hi", generate_audio=True,
        character_url="c://char", product_url="p://prod", style_urls=["kv://look"],
    )
    assert args["start_image_url"] == "start://u"
    assert args["aspect_ratio"] == "9:16"
    assert args["generate_audio"] is True
    assert args["shot_type"] == "intelligent"  # Kling AI Multi-Shot 자동 구조
    assert "image_url" not in args
    # elements: 캐릭터(@Element1), 제품(@Element2), 각각 frontal_image_url로 정체성 고정.
    assert args["elements"] == [
        {"frontal_image_url": "c://char", "reference_image_urls": ["c://char"]},
        {"frontal_image_url": "p://prod", "reference_image_urls": ["p://prod"]},
    ]
    # key_visual은 스타일 참조(image_urls, @Image1).
    assert args["image_urls"] == ["kv://look"]
    # 프롬프트에 @Element/@Image 태그 힌트가 실려 모델이 실제로 참조를 쓴다.
    assert "@Element1" in args["prompt"] and "@Element2" in args["prompt"]
    assert "@Image1" in args["prompt"]


def test_r2v_refs_capped_at_four_total():
    # elements + image_urls 합쳐 최대 4개. 스타일 참조가 넘치면 남은 예산만큼만 싣는다.
    args = _build_arguments(
        _R2V, "s", 6.0, "p", generate_audio=False,
        character_url="c", product_url="p2",
        style_urls=["s1", "s2", "s3", "s4"],
    )
    assert len(args["elements"]) == 2
    assert args["image_urls"] == ["s1", "s2"]  # 4 - 2(elements) = 2장만


def test_duration_clamped_to_kling_range():
    assert _build_arguments(_I2V, "u", 1.0, "", False)["duration"] == "3"  # 하한 3
    assert _build_arguments(_I2V, "u", 40.0, "", False)["duration"] == "15"  # 상한 15


def test_duration_rounds_up_never_short():
    # 계획 seg_dur이 분수면 올림해서 요청한다. 내림(round)이면 반환 클립이 계획보다 짧아져
    # 마지막 서브컷이 프리즈되고 세그먼트 경계 xfade가 깨져 다음 세그먼트가 통째 누락된다.
    assert _build_arguments(_I2V, "u", 9.494, "", False)["duration"] == "10"
    assert _build_arguments(_I2V, "u", 4.1, "", False)["duration"] == "5"
    assert _build_arguments(_I2V, "u", 6.0, "", False)["duration"] == "6"  # 정수는 그대로


def test_prompt_capped_to_kling_limit_keeping_shots():
    # Kling은 prompt 2500자 초과를 422로 거절한다 -> 한도 안으로 줄이되 샷 리스트는 보존해야 한다.
    head = "STYLE " + "x" * 3000  # 아주 긴 스타일 서술(앞부분)
    prompt = head + "\nShot 1: macro CU of the product.\nShot 2: medium, the creator."
    fit = _fit_prompt(prompt)
    assert len(fit) <= _MAX_PROMPT
    assert "Shot 1:" in fit and "Shot 2:" in fit  # 샷 리스트(끝)는 안 잘린다
    # 실제 인자에도 반영된다.
    args = _build_arguments(_I2V, "u", 6.0, prompt, False)
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


_PRO_R2V = "fal-ai/kling-video/o3/pro/reference-to-video"


def test_priority_picks_pro_ref2v_first_for_short_reel():
    # 우선순위 최상단이 pro reference-to-video면 15초 이하 릴은 pro가 쓰인다.
    env = {
        "VIDEO_MODEL_PRIORITY": f"fal:{_PRO_R2V},fal:{_R2V},fal:{_I2V}",
        "FAL_KEY": "k",
    }
    assert _select_video_model(env, total_dur=12.0) == _PRO_R2V


def test_priority_skips_ref2v_when_over_15s():
    # 15초를 넘으면 ref2v(pro/standard)는 건너뛰고 다음 후보(i2v)를 쓴다. 최상단이어도 무시.
    env = {
        "VIDEO_MODEL_PRIORITY": f"fal:{_PRO_R2V},fal:{_R2V},fal:{_I2V}",
        "FAL_KEY": "k",
    }
    assert _select_video_model(env, total_dur=20.0) == _I2V


def test_priority_ref2v_used_at_15s_boundary():
    # 정확히 15초는 단일 클립 한도 안이라 ref2v를 쓴다.
    env = {"VIDEO_MODEL_PRIORITY": f"fal:{_R2V},fal:{_I2V}", "FAL_KEY": "k"}
    assert _select_video_model(env, total_dur=15.0) == _R2V


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
