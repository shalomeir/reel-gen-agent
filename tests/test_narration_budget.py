"""나레이션 스크립트 예산 테스트: 대사량이 영상 길이에 맞춰지는지 검증(외부 호출 mock)."""

from __future__ import annotations

from reel_gen_agent.generate.planning_nodes import _narration_word_budget, narration_lines
from reel_gen_agent.generate.schema import InputMeta, ProductSpec, StyleDimensions


class _FakeTextClient:
    """프롬프트를 캡처하고 정해진 lines JSON을 돌려주는 mock TextClient."""

    def __init__(self, reply: str):
        self.reply = reply
        self.prompt: str | None = None

    def complete(self, prompt: str, temperature: float = 0.0) -> str:
        self.prompt = prompt
        return self.reply


def test_word_budget_scales_with_duration():
    # 영상이 길수록 예산(단어 수)이 커진다. 짧은 영상은 예산이 작아야 한다.
    short = _narration_word_budget(10.0)
    long = _narration_word_budget(30.0)
    assert short < long
    # 10초 영상은 19초 분량(33단어)의 대사를 허용하면 안 된다(리포트된 버그의 원인).
    assert short < 33


def test_prompt_states_word_budget_for_duration():
    # 프롬프트에 영상 길이 기반 단어 예산이 명시되어 LLM이 과다 대사를 쓰지 않게 한다.
    tc = _FakeTextClient('{"lines": []}')
    meta = InputMeta(duration_sec=10.0)
    beats = ["hook", "problem", "reveal", "use", "reaction", "proof", "cta"]
    narration_lines(tc, ProductSpec(name="Glow Serum"), StyleDimensions(), meta, beats)
    assert tc.prompt is not None
    assert str(_narration_word_budget(10.0)) in tc.prompt


def test_lines_trimmed_to_word_budget():
    # LLM이 예산을 무시하고 컷마다 긴 대사를 써도, 코드가 예산 초과분을 잘라 영상을 넘지 않게 한다.
    over = ", ".join(
        [f'"line number {i} has five words"' for i in range(7)]  # 각 6단어 x 7 = 42단어
    )
    tc = _FakeTextClient(f'{{"lines": [{over}]}}')
    meta = InputMeta(duration_sec=10.0)  # 예산 ~20단어
    beats = ["hook", "problem", "reveal", "use", "reaction", "proof", "cta"]
    lines = narration_lines(tc, ProductSpec(name="Glow Serum"), StyleDimensions(), meta, beats)
    total_words = sum(len(ln.text.split()) for ln in lines)
    assert total_words <= _narration_word_budget(10.0)
    assert len(lines) >= 1  # 적어도 한 줄은 남는다
