import json

import pytest

from reel_gen_agent.generate.hook import _extract_json, generate_hooks
from reel_gen_agent.generate.schema import HookRequest, ProductSpec
from reel_gen_agent.generate.text_client import StubTextClient


def _client(cands):
    return StubTextClient([json.dumps({"candidates": cands})])


def test_extract_json_strips_markdown_fence():
    raw = '```json\n{"candidates": []}\n```'
    assert json.loads(_extract_json(raw)) == {"candidates": []}


def test_extract_json_handles_prose_around_object():
    raw = 'Here you go:\n{"candidates": [1]}\nHope that helps!'
    assert json.loads(_extract_json(raw)) == {"candidates": [1]}


def test_generate_hooks_parses_fenced_llm_output():
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
    fenced = "```json\n" + json.dumps({"candidates": cands}) + "\n```"
    hs = generate_hooks(
        HookRequest(product=ProductSpec(name="s"), count=2), StubTextClient([fenced])
    )
    assert len(hs.candidates) == 2


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
