"""NanoBananaImageClient 실패 처리: 조용히 삼키지 않고 원인을 드러내고, 404 모델은 재시도에서
건너뛴다. 외부 호출(make_client/select_backend)은 가짜로 막아 결정론으로 검증한다.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from PIL import Image

from reel_gen_agent.generate import image_client as ic
from reel_gen_agent.generate.image_client import (
    NanoBananaImageClient,
    _is_not_found,
    _no_image_reason,
)


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _image_response() -> SimpleNamespace:
    part = SimpleNamespace(inline_data=SimpleNamespace(data=_png_bytes()))
    cand = SimpleNamespace(content=SimpleNamespace(parts=[part]), finish_reason="STOP")
    return SimpleNamespace(candidates=[cand], prompt_feedback=None)


def _no_image_response() -> SimpleNamespace:
    cand = SimpleNamespace(content=SimpleNamespace(parts=[]), finish_reason="SAFETY")
    return SimpleNamespace(candidates=[cand], prompt_feedback="blocked: safety")


def _single_backend(monkeypatch, behavior):
    """단일 백엔드(vertex)만 쓰도록 고정하고, 모델명 -> 응답/예외 behavior를 주입한다.

    make_client는 항상 같은 가짜 client를 돌려줘 여러 generate 호출에 걸친 호출 이력을
    한 곳에서 검사할 수 있게 한다.
    """
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(ic, "select_backend", lambda: ("vertex", {"project": "x"}))

    calls: list[str] = []

    def generate_content(model, contents, config=None):
        calls.append(model)
        return behavior(model)

    fake = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr(ic, "make_client", lambda selection: fake)
    return calls


def test_is_not_found_detects_404():
    assert _is_not_found(RuntimeError("404 NOT_FOUND: model missing"))
    assert _is_not_found(RuntimeError("Publisher model ... was NOT_FOUND"))
    assert not _is_not_found(RuntimeError("429 RESOURCE_EXHAUSTED"))


def test_no_image_reason_includes_finish_and_feedback():
    reason = _no_image_reason(_no_image_response())
    assert "finish_reason" in reason and "SAFETY" in reason
    assert "prompt_feedback" in reason and "safety" in reason


def test_generate_skips_not_found_hero_model_and_falls_back(monkeypatch, tmp_path):
    client = NanoBananaImageClient()

    def behavior(model):
        # 히어로 Pro 모델은 이 백엔드에 없다(404). 기본 모델(flash)은 성공한다.
        if model == client.hero_model:
            raise RuntimeError("404 NOT_FOUND: publisher model not available")
        return _image_response()

    calls = _single_backend(monkeypatch, behavior)

    out = client.generate("prompt", [], str(tmp_path / "a.png"), hero=True)
    assert (tmp_path / "a.png").exists() and out.endswith("a.png")
    # 404로 확인된 (백엔드, 히어로모델) 조합이 기록된다.
    assert ("vertex", client.hero_model) in client._unavailable
    assert client.last_error is None  # 최종 성공했으면 마지막 오류는 지운다.

    # 두 번째 호출에서는 404 히어로 모델을 아예 시도하지 않는다(반복 낭비 방지).
    calls.clear()
    client.generate("prompt", [], str(tmp_path / "b.png"), hero=True)
    assert client.hero_model not in calls
    assert client.model in calls


def test_generate_raises_informative_error_with_cause(monkeypatch, tmp_path):
    client = NanoBananaImageClient()

    def behavior(model):
        raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")

    _single_backend(monkeypatch, behavior)

    with pytest.raises(RuntimeError, match="429 RESOURCE_EXHAUSTED"):
        client.generate("prompt", [], str(tmp_path / "c.png"))
    # 마지막 실패 사유를 남겨 호출 측(플랜)이 사용자에게 보여줄 수 있게 한다.
    assert client.last_error is not None
    assert "429" in str(client.last_error)


def test_generate_surfaces_safety_block_reason(monkeypatch, tmp_path):
    client = NanoBananaImageClient()
    _single_backend(monkeypatch, lambda model: _no_image_response())

    with pytest.raises(RuntimeError, match="이미지 없는 응답"):
        client.generate("prompt", [], str(tmp_path / "d.png"))
