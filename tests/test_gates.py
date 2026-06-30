from reel_gen_agent.generate.gates import GateConfig, resolve_gate


def test_run_mode_auto_passes_without_asking():
    called = []
    out = resolve_gate(GateConfig(mode="run"), "hook", lambda: called.append(1) or "confirm")
    assert out == "pass"
    assert called == []


def test_force_pass_skips_one_step():
    cfg = GateConfig(mode="ask", force_pass={"storyboard"})
    assert resolve_gate(cfg, "storyboard", lambda: "confirm") == "pass"


def test_ask_mode_calls_ask_fn():
    cfg = GateConfig(mode="ask")
    assert resolve_gate(cfg, "hook", lambda: "edit") == "edit"
