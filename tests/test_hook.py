import json

import pytest

from reel_gen_agent.generate.hook import generate_hooks
from reel_gen_agent.generate.schema import HookRequest, ProductSpec
from reel_gen_agent.generate.text_client import StubTextClient


def _client(cands):
    return StubTextClient([json.dumps({"candidates": cands})])


def test_window_is_three_seconds_for_long_video():
    cands = [
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
    hs = generate_hooks(
        HookRequest(product=ProductSpec(name="serum"), duration_sec=18, count=2), _client(cands)
    )
    assert hs.candidates[0].window_sec == (0.0, 3.0)


def test_window_compressed_for_short_video():
    cands = [
        {
            "hook_type": "H1",
            "headline": "x",
            "visual_direction": "v",
            "bridge": "b",
            "variant": "question",
        },
        {
            "hook_type": "H1",
            "headline": "y",
            "visual_direction": "v",
            "bridge": "b",
            "variant": "command",
        },
    ]
    hs = generate_hooks(
        HookRequest(product=ProductSpec(name="s"), duration_sec=8, count=2), _client(cands)
    )
    assert hs.candidates[0].window_sec == (0.0, pytest.approx(1.6))


def test_unknown_hook_type_rejected():
    cands = [{"hook_type": "H99", "headline": "x", "visual_direction": "v", "bridge": "b"}]
    with pytest.raises(ValueError):
        generate_hooks(HookRequest(product=ProductSpec(name="s"), count=1), _client(cands))


def test_low_fit_requires_bridge():
    cands = [{"hook_type": "H12", "headline": "A or B?", "visual_direction": "v", "bridge": ""}]
    with pytest.raises(ValueError):
        generate_hooks(HookRequest(product=ProductSpec(name="s"), count=1), _client(cands))
