"""storyboard 노드 테스트. 콘티/패널은 항상, 컷별 이미지는 복잡한 멀티컷일 때만.

외부 호출 없는 결정론 검증 + StubImageClient로 이미지 단계를 막는다.
"""

from reel_gen_agent.generate.image_client import StubImageClient
from reel_gen_agent.generate.schema import (
    EnvironmentSpec,
    HookCandidate,
    InputMeta,
    ModelSpec,
    ProductSpec,
    StyleDimensions,
)
from reel_gen_agent.generate.storyboard import (
    build_storyboard,
    generate_panel_images,
    needs_panel_images,
)


def _parts(pacing="mixed", duration=18.0, hook=True):
    style = StyleDimensions(pacing=pacing, palette=["#fff", "#f0c"])
    if hook:
        style.hook = HookCandidate(hook_type="H1", headline="Glow in seconds")
    return dict(
        meta=InputMeta(duration_sec=duration),
        style=style,
        product=ProductSpec(name="Glow Serum", usp="dewy glow", affordances=["spritz"]),
        character=ModelSpec(look="dewy skin, warm vibe"),
        environment=EnvironmentSpec(location="bright vanity", lighting="soft daylight"),
    )


def test_face_beauty_product_frames_tighter():
    """얼굴용 뷰티 제품이면 더 타이트(얼굴 중심) 프레이밍을 콘티에 박는다."""
    parts = _parts()
    parts["product"] = ProductSpec(name="Glow Serum")
    sb = build_storyboard(**parts)
    assert "face fills most" in (sb.global_prompt or "")


def test_non_face_product_defaults_to_upper_body():
    parts = _parts()
    parts["product"] = ProductSpec(name="Canvas Tote Bag")
    sb = build_storyboard(**parts)
    assert "upper body only" in (sb.global_prompt or "")


def test_storyboard_always_has_panels_and_hook_first():
    sb = build_storyboard(**_parts())
    assert len(sb.panels) >= 2
    assert sb.panels[0].beat == "hook"
    assert sb.panels[0].t_start == 0.0
    assert sb.panels[0].subtitle_text == "Glow in seconds"
    assert sb.global_prompt  # 콘티 공통 맥락이 채워진다


def test_fast_pacing_makes_more_cuts_than_slow():
    fast = build_storyboard(**_parts(pacing="fast_montage", duration=18.0))
    slow = build_storyboard(**_parts(pacing="slow_demo", duration=18.0))
    assert len(fast.panels) > len(slow.panels)


def test_timing_covers_duration_without_overrun():
    sb = build_storyboard(**_parts(duration=12.0))
    assert sb.panels[-1].t_end <= 12.0 + 0.05


def test_simple_video_does_not_need_panel_images():
    # 짧고 단순한(컷 적은) 영상은 컷별 이미지가 불필요.
    sb = build_storyboard(**_parts(pacing="slow_demo", duration=8.0))
    assert needs_panel_images(sb) is False


def test_complex_multicut_needs_panel_images():
    # 길고 빠른 컷(컷 많고 샷 타입 다양)이면 컷별 이미지가 필요.
    sb = build_storyboard(**_parts(pacing="fast_montage", duration=24.0))
    assert needs_panel_images(sb) is True


def test_generate_panel_images_fills_stills_with_refs(tmp_path):
    sb = build_storyboard(**_parts(pacing="fast_montage", duration=24.0))
    client = StubImageClient()
    generate_panel_images(
        sb,
        character_image="char.png",
        product_image="prod.png",
        image_client=client,
        out_dir=str(tmp_path),
    )
    assert all(p.still_image for p in sb.panels)
    # 캐릭터·제품 이미지를 reference로 함께 넘긴다.
    assert client.calls[0][1] == ["char.png", "prod.png"]
