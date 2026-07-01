"""환경 노드 테스트(결정론 경로, LLM 없이)."""

from reel_gen_agent.generate.environment import DEFAULT_ENVIRONMENT, derive_environment
from reel_gen_agent.generate.schema import ProductSpec


def test_defaults_without_llm():
    env = derive_environment("skincare reel", ProductSpec(name="serum"), None, text_client=None)
    assert env.location == DEFAULT_ENVIRONMENT.location


def test_llm_location_is_used():
    class _Client:
        def complete(self, prompt, temperature=0.7):
            return '{"location": "a sunny outdoor rooftop cafe", "lighting": "golden hour", "mood": "airy"}'

    env = derive_environment("summer glow reel outdoors", ProductSpec(name="mist"), None, _Client())
    assert "rooftop" in (env.location or "")
    assert env.mood == "airy"
