"""기획·카피 LLM 클라이언트. 1차 Gemini 3.1 Pro(Vertex 우선), 옵션 Claude.

[ai-model-records.md] §2: 텍스트 레인은 Gemini 3.1 Pro와 Claude Opus를 일급으로 둔다.
`TEXT_MODEL_PRIORITY`(예: "gemini,claude")로 우선순위를 고른다. 스토리보드/스크립트 노드가
이 클라이언트로 실제 LLM을 부른다. 테스트는 StubTextClient로 호출을 막는다.
"""

from __future__ import annotations

import os
from typing import Protocol


class TextClient(Protocol):
    def complete(self, prompt: str, *, temperature: float = 0.9) -> str: ...


class StubTextClient:
    """정해 둔 응답을 순서대로 돌려주는 테스트용 클라이언트."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def complete(self, prompt: str, *, temperature: float = 0.9) -> str:
        return self._responses.pop(0)


class GeminiTextClient:
    """Gemini 텍스트 클라이언트. 분석 계층 플러밍을 재사용한다(Vertex 우선, GEMINI 폴백)."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("GEMINI_TEXT_MODEL") or "gemini-3.1-pro-preview"

    def complete(self, prompt: str, *, temperature: float = 0.9) -> str:
        from google.genai import types

        from ..analysis.gemini_client import make_client, select_backend

        selection = select_backend()
        if selection is None:
            raise RuntimeError("Gemini 자격 없음(GEMINI_API_KEY 또는 Vertex 자격 필요)")
        client = make_client(selection)
        resp = client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=temperature),
        )
        return resp.text or ""


class ClaudeTextClient:
    """Claude 텍스트 클라이언트(옵션). `ANTHROPIC_API_KEY`와 anthropic 패키지가 필요하다."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("CLAUDE_MODEL") or "claude-opus-4-8"

    def complete(self, prompt: str, *, temperature: float = 0.9) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        msg = client.messages.create(
            model=self.model,
            max_tokens=2048,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        # content는 블록 리스트. 텍스트 블록만 이어 붙인다.
        return "".join(getattr(b, "text", "") for b in msg.content)


def _gemini_available() -> bool:
    return bool(
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or (
            os.environ.get("GOOGLE_CLOUD_PROJECT")
            and os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        )
    )


def _claude_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def make_text_client() -> TextClient | None:
    """`TEXT_MODEL_PRIORITY` 순서로 가용한 첫 클라이언트를 만든다. 없으면 None.

    기본 우선순위는 gemini,claude. 각 항목이 "gemini"/"claude"(계열)거나 모델 ID일 수 있다.
    """
    priority = (os.environ.get("TEXT_MODEL_PRIORITY") or "gemini,claude").lower()
    order = [p.strip() for p in priority.split(",") if p.strip()]
    for item in order:
        if ("claude" in item or "opus" in item or "sonnet" in item) and _claude_available():
            return ClaudeTextClient()
        if ("gemini" in item) and _gemini_available():
            return GeminiTextClient()
    # 우선순위 이름이 모델 ID 형태일 때: Gemini부터 시도.
    if _gemini_available():
        return GeminiTextClient()
    if _claude_available():
        return ClaudeTextClient()
    return None
