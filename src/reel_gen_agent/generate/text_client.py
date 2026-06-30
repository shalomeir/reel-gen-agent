"""기획·카피 LLM 클라이언트 인터페이스. 실제 백엔드(Gemini/Claude)는 .env로 고른다.

테스트는 StubTextClient로 호출을 막는다([ai-model-records.md] §2, TEXT_MODEL_PRIORITY).
"""

from __future__ import annotations

from typing import Protocol


class TextClient(Protocol):
    def complete(self, prompt: str, *, temperature: float = 0.9) -> str: ...


class StubTextClient:
    """정해 둔 응답을 순서대로 돌려주는 테스트용 클라이언트."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def complete(self, prompt: str, *, temperature: float = 0.9) -> str:
        return self._responses.pop(0)
