"""챗 인테이크 대화 판단 테스트(순수 함수)."""

from __future__ import annotations

from reel_gen_agent.generate.chat_intake import ChatState, next_turn


class _FakeTC:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def complete(self, prompt: str, temperature: float = 0.5) -> str:
        # 대화 기록이 프롬프트에 실려야 한다.
        assert "Conversation so far" in prompt
        return self._payload


def test_next_turn_asks_when_not_ready():
    s = ChatState()
    s.add_user("영상 하나 만들고 싶어")
    d = next_turn(s, _FakeTC('{"ready": false, "question": "어떤 제품인가요?", "brief": ""}'))
    assert d.ready is False
    assert "제품" in d.question


def test_next_turn_consolidates_brief_when_ready():
    s = ChatState()
    s.add_user("글로우 세럼으로 아침 루틴 릴")
    s.add_assistant("참고할 영상이 있나요?")
    s.add_user("응 ref.mp4")
    d = next_turn(
        s,
        _FakeTC('{"ready": true, "question": "", "brief": "제품: glow serum. 목적: 아침 루틴. reference: ref.mp4"}'),
    )
    assert d.ready is True
    assert "glow serum" in d.brief and "reference" in d.brief


def test_next_turn_falls_back_on_bad_json():
    s = ChatState()
    s.add_user("hi")
    d = next_turn(s, _FakeTC("not json at all"))
    assert d.ready is False and d.question  # 대화가 끊기지 않게 후속 질문


def test_transcript_labels_roles():
    s = ChatState()
    s.add_user("hello")
    s.add_assistant("hi there")
    t = s.transcript()
    assert "User: hello" in t and "Assistant: hi there" in t
