"""style 저술·보정 노드 테스트. LLM 호출은 StubTextClient로 결정론화한다."""

import json

from reel_gen_agent.generate.plan_graph import _style_node, _style_refine_node
from reel_gen_agent.generate.schema import (
    HookCandidate,
    InputMeta,
    ModelSpec,
    Objective,
    ProductSpec,
    Provenance,
    Storyboard,
    StoryboardPanel,
    StyleDimensions,
)
from reel_gen_agent.generate.style import (
    _reference_insight,
    author_style,
    ensure_style_defaults,
)
from reel_gen_agent.generate.text_client import StubTextClient


class _CapturingClient:
    """complete에 들어온 프롬프트를 잡아 두고 고정 JSON을 돌려준다(프롬프트 내용 검증용)."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt = ""

    def complete(self, prompt: str, *, temperature: float = 0.9) -> str:
        self.prompt = prompt
        return self.response


class _NullTracer:
    """노드가 여는 span 컨텍스트만 흉내 낸다(로깅 없음)."""

    def node(self, *args, **kwargs):
        class _Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()


def _state(**over):
    base = {
        "tracer": _NullTracer(),
        "objective": Objective(goal="15s serum unboxing"),
        "product": ProductSpec(name="Glow Serum"),
        "character": ModelSpec(),
        "meta": InputMeta(duration_sec=15.0),
        "style": StyleDimensions(),
        "provenance": Provenance(style_source="llm"),
        "text_client": None,
    }
    base.update(over)
    return base


def _style_json(**over):
    data = {
        "tone": ["sensorial", "glowing"],
        "pacing": "fast_montage",
        "motion": "gentle",
        "palette": ["peach", "cream"],
        "realism": "hyper_realistic",
    }
    data.update(over)
    return json.dumps(data)


def test_author_style_applies_valid_fields_and_preserves_hook():
    hook = HookCandidate(hook_type="H1", headline="Glow", visual_direction="macro")
    base = StyleDimensions(hook=hook)
    out = author_style(
        StubTextClient([_style_json()]),
        objective=Objective(goal="g"),
        product=ProductSpec(name="p"),
        character=ModelSpec(),
        meta=InputMeta(),
        base=base,
    )
    assert out.tone == ["sensorial", "glowing"]
    assert out.pacing == "fast_montage"
    assert out.motion == "gentle"
    assert out.hook is hook or out.hook.headline == "Glow"  # hook 보존


def test_author_style_ignores_out_of_enum_values():
    out = author_style(
        StubTextClient([_style_json(pacing="turbo", motion="wild")]),
        objective=Objective(goal="g"),
        product=ProductSpec(name="p"),
        character=ModelSpec(),
        meta=InputMeta(),
        base=StyleDimensions(pacing="mixed", motion="still"),
    )
    # enum 밖 값은 무시하고 base를 유지한다.
    assert out.pacing == "mixed"
    assert out.motion == "still"


def test_ensure_style_defaults_never_empty():
    sb = Storyboard(panels=[StoryboardPanel(index=i) for i in range(10)])
    out = ensure_style_defaults(StyleDimensions(), sb, InputMeta(duration_sec=10.0))
    assert out.tone  # 비어 있지 않다
    assert out.pacing == "fast_montage"  # 컷 10개/10초 -> 1.0s -> fast
    assert out.motion == "gentle"


def test_style_node_authors_when_no_reference():
    st = _state(text_client=StubTextClient([_style_json()]))
    out = _style_node(st)["style"]
    assert out.tone == ["sensorial", "glowing"]
    assert out.pacing == "fast_montage"


def test_style_node_keeps_measured_reference_style():
    measured = StyleDimensions(tone=["measured"], pacing="slow_demo", motion="still")
    st = _state(
        style=measured,
        provenance=Provenance(style_source="reference"),
        text_client=StubTextClient([_style_json()]),  # 호출되면 안 된다
    )
    out = _style_node(st)["style"]
    assert out.tone == ["measured"]  # 측정값 보존, 덮이지 않음
    assert out.pacing == "slow_demo"


def test_style_node_defaults_without_llm():
    st = _state(text_client=None)
    out = _style_node(st)["style"]
    assert out.tone  # LLM 없어도 비지 않는다
    assert out.pacing


def test_style_refine_noop_for_reference():
    st = _state(
        provenance=Provenance(style_source="reference"),
        text_client=StubTextClient([_style_json()]),
    )
    assert _style_refine_node(st) == {}  # 레퍼런스는 보정하지 않는다


def test_style_refine_authors_for_no_reference():
    sb = Storyboard(panels=[StoryboardPanel(index=0, beat="hook")])
    st = _state(text_client=StubTextClient([_style_json(tone=["refined"])]), storyboard=sb)
    out = _style_refine_node(st)["style"]
    assert out.tone == ["refined"]


def test_reference_insight_loads_from_docs():
    # docs/refer-insight.md가 레포에 있으므로 로더가 내용을 읽어 온다.
    insight = _reference_insight()
    assert insight  # 비어 있지 않다
    assert "파라미터" in insight  # 스타일 축 관련 섹션이 들어 있다


def test_author_style_prompt_includes_reference_insight():
    # 인사이트가 있으면 style 저술 프롬프트에 방향 참고로 실린다.
    client = _CapturingClient(_style_json())
    author_style(
        client,
        objective=Objective(goal="g"),
        product=ProductSpec(name="p"),
        character=ModelSpec(),
        meta=InputMeta(),
        base=StyleDimensions(),
    )
    assert "Cross-reference insights" in client.prompt
    assert "파라미터" in client.prompt  # 실제 인사이트 본문이 주입됐다
