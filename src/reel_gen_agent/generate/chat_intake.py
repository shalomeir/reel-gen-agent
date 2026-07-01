"""챗 인테이크: LLM 주도 대화로 ReelProfile용 브리프를 모은다.

chat 모드는 입력 없이 시작해 "어떤 숏폼 영상을 만들까요?"로 열고, 필요한 것(목적·제품·
레퍼런스·바이브 등)을 한 번에 하나씩 자연스럽게 물어보며 채운다. 충분해지면 대화를 하나의
브리프로 종합한다. 이 모듈은 '다음 한 턴'을 정하는 순수 함수라 대화 UI(prompt_toolkit)와
분리돼 테스트 가능하다(specs/product-design.md 챗 모드).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .text_client import TextClient

# 입력 없이 시작할 때 여는 첫 질문.
OPENING = (
    "어떤 숏폼 영상을 만들고 싶으세요? 제품과 목적, 참고할 영상이나 스타일이 있으면 "
    "자유롭게 말씀해 주세요."
)

_PROMPT = (
    "You are a friendly assistant helping a creator spec a vertical short-form video ad. Gather, "
    "ONE natural question at a time, what is needed to plan it: the video's PURPOSE/goal (required), "
    "the product, the CHARACTER/model who appears on camera, any reference video or style, and the "
    "desired vibe/tone. Keep it light and conversational, in the user's language.\n"
    "IMPORTANT: after you have the purpose and product, you MUST ask once about the character/model "
    "who appears in the video (who they are, their look/vibe, or a reference image) before you are "
    "ready. If the user says to leave it up to you, accept that and note it in the brief. Never "
    "silently invent a character without asking. Stop asking once you have a clear purpose, a "
    "product, and the character settled (specified or explicitly deferred); do not over-ask "
    "(3-6 exchanges is plenty).\n"
    "Conversation so far:\n{convo}\n\n"
    'Reply raw JSON only (no markdown): {{"ready": bool, "question": str, "brief": str}}. '
    "If NOT ready: 'question' = your next single question in the user's language, 'brief' = \"\". "
    "If ready: 'question' = \"\", 'brief' = one consolidated brief string for the generator that "
    "states the purpose and, when known, adds labeled fields ('제품: ...', 'reference: ...', "
    "'캐릭터: ...') plus a short tone/vibe note."
)


@dataclass
class ChatState:
    """대화 기록(역할, 텍스트). role은 'user' 또는 'assistant'."""

    turns: list[tuple[str, str]] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        self.turns.append(("user", text))

    def add_assistant(self, text: str) -> None:
        self.turns.append(("assistant", text))

    def transcript(self) -> str:
        return "\n".join(
            f"{'User' if role == 'user' else 'Assistant'}: {text}" for role, text in self.turns
        )


@dataclass
class ChatDecision:
    ready: bool
    question: str
    brief: str


def _extract_json(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


def next_turn(state: ChatState, text_client: TextClient) -> ChatDecision:
    """대화 상태에서 다음 한 턴을 정한다: 아직이면 다음 질문, 충분하면 종합 브리프.

    LLM 호출/파싱 실패 시 아직 안 됐다고 보고 일반적 후속 질문을 돌려준다(대화가 끊기지 않게).
    """
    try:
        raw = text_client.complete(_PROMPT.format(convo=state.transcript()), temperature=0.5)
        data = json.loads(_extract_json(raw))
    except Exception:
        return ChatDecision(ready=False, question="조금 더 자세히 말씀해 주시겠어요?", brief="")
    return ChatDecision(
        ready=bool(data.get("ready", False)),
        question=str(data.get("question") or "").strip(),
        brief=str(data.get("brief") or "").strip(),
    )
