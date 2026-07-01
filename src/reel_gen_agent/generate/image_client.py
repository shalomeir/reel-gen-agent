"""이미지 생성 클라이언트 인터페이스. 실제 백엔드(Nano Banana/FLUX)는 .env로 고른다.

스토리보드 컷별 start image와 에셋 시트가 이걸 쓴다. 테스트는 StubImageClient로 호출을
막는다([ai-model-records.md] §3). 캐릭터·제품 reference 이미지를 함께 넘겨 일관성을 잡는다.
"""

from __future__ import annotations

import base64
import os
from typing import Protocol

# 이미지 생성 백엔드 선택/클라이언트는 분석 계층 플러밍을 재사용한다(Vertex 우선, GEMINI 폴백).
from ..analysis.gemini_client import make_client, select_backend

DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"


class ImageClient(Protocol):
    def generate(self, prompt: str, refs: list[str], out_path: str) -> str:
        """프롬프트와 reference 이미지들로 이미지를 만들어 out_path에 저장하고 경로를 돌려준다."""
        ...


class StubImageClient:
    """정해 둔 경로에 빈 파일을 쓰는 테스트용 클라이언트(외부 호출 없음)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], str]] = []

    def generate(self, prompt: str, refs: list[str], out_path: str) -> str:
        self.calls.append((prompt, refs, out_path))
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("stub-image")
        return out_path


class NanoBananaImageClient:
    """Gemini 이미지(나노바나나) 실제 백엔드. 캐릭터·제품 reference로 일관성을 잡는다.

    모델은 .env `GEMINI_IMAGE_MODEL`(기본 gemini-3.1-flash-image-preview). 백엔드/응답
    모달리티 조합을 차례로 시도하고, 끝까지 이미지를 못 얻으면 RuntimeError를 던져 호출
    측이 폴백(에셋 이미지 재사용)하게 한다.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("GEMINI_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL

    def _selections(self) -> list[tuple[str, dict]]:
        selections: list[tuple[str, dict]] = []
        primary = select_backend()
        if primary:
            selections.append(primary)
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if key and not any(s[0] == "gemini" for s in selections):
            selections.append(("gemini", {"api_key": key}))
        return selections

    @staticmethod
    def _extract_bytes(response) -> bytes | None:
        for cand in getattr(response, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline else None
                if data:
                    return base64.b64decode(data) if isinstance(data, str) else data
        return None

    def generate(self, prompt: str, refs: list[str], out_path: str) -> str:
        from google.genai import types

        contents: list = []
        for ref in refs:
            if ref and os.path.exists(ref):
                with open(ref, "rb") as fh:
                    contents.append(types.Part.from_bytes(data=fh.read(), mime_type="image/jpeg"))
        contents.append(prompt)

        # 이미지 모델은 기본이 이미지 응답이지만, 일부는 response_modalities 명시가 필요하다.
        configs: list = [
            None,
            types.GenerateContentConfig(response_modalities=["IMAGE"]),
            types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        ]
        for selection in self._selections():
            try:
                client = make_client(selection)
            except Exception:
                continue
            for config in configs:
                try:
                    kwargs = {"model": self.model, "contents": contents}
                    if config is not None:
                        kwargs["config"] = config
                    response = client.models.generate_content(**kwargs)
                except Exception:
                    continue
                data = self._extract_bytes(response)
                if data:
                    # PNG로 정규화해 저장(ffmpeg 입력 안정성).
                    import io

                    from PIL import Image

                    Image.open(io.BytesIO(data)).convert("RGB").save(out_path)
                    return out_path
        raise RuntimeError("nano banana 이미지 생성 실패(모든 백엔드/모달리티)")
