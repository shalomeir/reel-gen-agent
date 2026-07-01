import json

import pytest

from reel_gen_agent.generate.planning_graph import run_planning
from reel_gen_agent.generate.schema import ReelProfile
from reel_gen_agent.generate.text_client import StubTextClient


def test_run_planning_writes_valid_reel_profile(tmp_path):
    cands = {
        "candidates": [
            {
                "hook_type": "H1",
                "headline": "Glow",
                "visual_direction": "macro",
                "bridge": "serum",
                "variant": "question",
            },
            {
                "hook_type": "H1",
                "headline": "Glow now",
                "visual_direction": "macro",
                "bridge": "serum",
                "variant": "command",
            },
        ]
    }
    client = StubTextClient([json.dumps(cands)])
    # 제품은 텍스트 이름으로 준다(URL이면 실제 판매 페이지 스크래핑이 필요하고, 못 읽으면
    # 가짜를 지어내지 않고 실패하는 게 계약이다). 이 테스트는 프로필 생성 자체를 검증한다.
    path = run_planning(
        "발랄한 15초 언박싱 릴. 제품: 글로우세럼",
        str(tmp_path / "outputs"),
        text_client=client,
    )
    assert path.name.startswith("ReelProfile-")
    profile = ReelProfile.model_validate_json(path.read_text(encoding="utf-8"))
    assert profile.objective.goal


def test_missing_objective_raises(tmp_path):
    with pytest.raises(ValueError):
        run_planning("", str(tmp_path / "outputs"))


def test_unscrapable_product_url_raises_not_fabricates(tmp_path, monkeypatch):
    # 실제 제품 URL을 못 읽으면 브리프로 '가짜 제품'을 지어내지 말고 명확히 실패해야 한다.
    import contextlib

    from reel_gen_agent.generate import plan_graph as pg
    from reel_gen_agent.generate import product_source
    from reel_gen_agent.generate.schema import ProductSpec, StyleDimensions

    monkeypatch.setattr(product_source, "collect_materials", lambda url, out: None)

    class _T:
        run_id = "t"

        def node(self, *a, **k):
            return contextlib.nullcontext()

    url = "https://shop.example/store/goods?goodsNo=A1"
    state = {
        "objective": type("O", (), {"goal": f"데일리 릴. 제품: {url}"})(),
        "product": ProductSpec(name="product"),
        "product_url": url,
        "product_image": "",
        "ref_product": None,
        "text_client": None,
        "image_client": None,
        "style": StyleDimensions(),
        "outputs_root": str(tmp_path / "outputs"),
        "tracer": _T(),
    }
    with pytest.raises(ValueError, match="제품 URL"):
        pg._product_node(state)


def test_no_product_source_raises_not_fabricates(tmp_path):
    # 제품 URL·이미지·사용자 이름이 모두 없으면 제품을 지어내지 말고 확보 실패로 알려야 한다.
    import contextlib

    from reel_gen_agent.generate import plan_graph as pg
    from reel_gen_agent.generate.product import ProductGroundingError
    from reel_gen_agent.generate.schema import ProductSpec, StyleDimensions

    class _T:
        run_id = "t"

        def node(self, *a, **k):
            return contextlib.nullcontext()

    state = {
        "objective": type("O", (), {"goal": "감성적인 무드 릴 만들어줘"})(),
        "product": ProductSpec(name="product"),  # intake 자리표시자(이름 없음)
        "product_url": "",
        "product_image": "",
        "ref_product": None,
        "text_client": None,
        "image_client": None,
        "style": StyleDimensions(),
        "outputs_root": str(tmp_path / "outputs"),
        "tracer": _T(),
    }
    with pytest.raises(ProductGroundingError):
        pg._product_node(state)


def test_music_runs_after_narration_last():
    # music은 확정 훅·스토리·나레이션을 보고 정하도록 plan의 마지막(narration 다음)에 온다.
    from reel_gen_agent.generate.plan_graph import build_plan_graph

    edges = {(e.source, e.target) for e in build_plan_graph().get_graph().edges}
    assert ("narration", "music") in edges
    assert ("music", "write_profile") in edges
    # style 초안은 hook·story 앞, style 보정은 story 뒤(narration 앞)에 온다.
    assert ("environment", "style") in edges
    assert ("style", "hook") in edges
    assert ("style_refine", "narration") in edges
    # 옛 배선이 남아 있지 않아야 한다.
    assert ("environment", "hook") not in edges
    assert ("environment", "music") not in edges
    assert ("music", "hook") not in edges
