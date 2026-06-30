"""게이트 일반화: ask(챗 확인/수정) / pass(force-step-pass) / run(전부 통과).

모든 중요한 노드 뒤에 같은 추상을 둔다([ADR.md] ADR-0007). ask_fn을 주입해 UI와 분리한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class GateConfig:
    mode: str = "run"  # ask / run
    force_pass: set[str] = field(default_factory=set)


def resolve_gate(config: GateConfig, step: str, ask_fn: Callable[[], str]) -> str:
    if config.mode == "run" or step in config.force_pass:
        return "pass"
    return ask_fn()
