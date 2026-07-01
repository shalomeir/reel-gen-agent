"""InputMeta 포맷 기본값과 가드레일 테스트.

계약은 specs/trd.md "영상 포맷 기본값과 가드레일". 외부 호출이 없는 순수 결정론
검증이라 전부 실제 단언으로 덮는다.
"""

import pytest
from pydantic import ValidationError

from reel_gen_agent.generate.schema import (
    AssetView,
    GenerationInput,
    HookCandidate,
    InputMeta,
    NodeRun,
    Objective,
    ProductionPlan,
    ProductSpec,
    ReelProfile,
    RunManifest,
)


def test_defaults_match_spec():
    """기본값: 14초(기본 제작 포맷), 9:16, 1080x1920, 30fps."""
    m = InputMeta()
    assert m.duration_sec == 14.0
    assert m.aspect_ratio == "9:16"
    assert m.width == 1080
    assert m.height == 1920
    assert m.fps == 30
    assert m.resolution == "1080x1920"


def test_default_duration_is_short_form_format():
    """기본 제작 포맷은 14초(7초 멀티샷 2개)다."""
    assert InputMeta().duration_sec == 14.0


@pytest.mark.parametrize("dur", [15.0, 18.0, 22.0, 60.0, 1.0])
def test_duration_within_range_ok(dur):
    assert InputMeta(duration_sec=dur).duration_sec == dur


@pytest.mark.parametrize("dur", [60.1, 90.0, 120.0, 0.0, -5.0])
def test_duration_out_of_range_rejected(dur):
    """60초 초과(하드 상한)와 비양수 길이는 거부한다."""
    with pytest.raises(ValidationError):
        InputMeta(duration_sec=dur)


@pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
def test_fps_allowed(fps):
    assert InputMeta(fps=fps).fps == fps


@pytest.mark.parametrize("fps", [23, 29, 45, 120])
def test_fps_rejected(fps):
    with pytest.raises(ValidationError):
        InputMeta(fps=fps)


@pytest.mark.parametrize("ratio", ["1:1", "16:9", "4:5", "9:18"])
def test_aspect_ratio_rejected(ratio):
    with pytest.raises(ValidationError):
        InputMeta(aspect_ratio=ratio)


@pytest.mark.parametrize("w,h", [(1080, 1920), (720, 1280), (540, 960)])
def test_lower_resolution_allowed(w, h):
    """1080p 이하의 더 낮은 해상도는 사유가 있을 때 허용한다(9:16 유지)."""
    m = InputMeta(width=w, height=h)
    assert (m.width, m.height) == (w, h)


@pytest.mark.parametrize("w,h", [(2160, 3840), (1440, 2560), (1081, 1921)])
def test_upscale_beyond_1080p_rejected(w, h):
    """1080x1920 초과(업스케일)는 거부한다."""
    with pytest.raises(ValidationError):
        InputMeta(width=w, height=h)


@pytest.mark.parametrize("w,h", [(1080, 1080), (1080, 1350), (720, 720)])
def test_non_9_16_resolution_rejected(w, h):
    """9:16 비율을 벗어난 해상도는 거부한다."""
    with pytest.raises(ValidationError):
        InputMeta(width=w, height=h)


def test_zero_resolution_rejected():
    with pytest.raises(ValidationError):
        InputMeta(width=0, height=0)


def test_generation_input_uses_meta_defaults():
    """GenerationInput이 기본 InputMeta를 그대로 받는다."""
    gi = GenerationInput(product=ProductSpec(name="serum"))
    assert gi.meta.duration_sec == 14.0
    assert gi.meta.fps == 30
    assert gi.meta.resolution == "1080x1920"


# --- ReelProfile (plan/execute 경계 계약) -------------------------------------


def test_reel_profile_minimal_requires_objective_and_product():
    """ReelProfile은 objective와 product가 필수다."""
    rp = ReelProfile(
        objective=Objective(goal="제품 광고 릴"),
        product=ProductSpec(name="serum"),
    )
    assert rp.objective.goal == "제품 광고 릴"
    assert rp.meta.resolution == "1080x1920"
    # voice는 되도록 사용하되 기본 전달은 나레이션(voiceover)
    assert rp.narration.delivery == "voiceover"


def test_reel_profile_roundtrip():
    """ReelProfile은 JSON 직렬화/역직렬화로 동일하게 재구성된다(이식 경계)."""
    rp = ReelProfile(
        objective=Objective(goal="언박싱 릴"),
        product=ProductSpec(name="serum", affordances=["짜다", "바르다"]),
    )
    dumped = rp.model_dump_json()
    restored = ReelProfile.model_validate_json(dumped)
    assert restored == rp
    assert restored.product.affordances == ["짜다", "바르다"]


def test_objective_requires_goal():
    with pytest.raises(ValidationError):
        Objective()  # type: ignore[call-arg]


def test_hook_candidate_rejects_unknown_type():
    """후크 유형은 H1~H12만 허용한다(hook-generator.md 계약)."""
    HookCandidate(hook_type="H1")  # ok
    with pytest.raises(ValidationError):
        HookCandidate(hook_type="H99")


def test_asset_view_defaults_unsatisfied():
    """필수 뷰는 기본 미충족이라 게이트가 충족을 강제로 확인하게 한다."""
    v = AssetView(name="face_closeup")
    assert v.required is True
    assert v.satisfied is False


def test_run_manifest_carries_production_plan():
    """ProductionPlan은 ReelProfile이 아니라 RunManifest에 실린다(이식 의도 분리)."""
    manifest = RunManifest(
        run_id="glow-serum-20260630-204512",
        nodes=[NodeRun(name="video", prompt="a serum on a table")],
        production_plan=ProductionPlan(
            video_model="veo-3.1-lite-generate-001",
            voice_strategy="integrated",
            fallbacks_applied=["no_fal_key->veo_only"],
        ),
    )
    assert manifest.production_plan is not None
    assert manifest.production_plan.voice_strategy == "integrated"
    assert manifest.nodes[0].prompt == "a serum on a table"
