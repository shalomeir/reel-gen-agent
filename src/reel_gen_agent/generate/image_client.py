"""이미지 생성 클라이언트 인터페이스. 실제 백엔드(Nano Banana/FLUX)는 .env로 고른다.

스토리보드 컷별 start image와 에셋 시트가 이걸 쓴다. 테스트는 StubImageClient로 호출을
막는다([ai-model-records.md] §3). 캐릭터·제품 reference 이미지를 함께 넘겨 일관성을 잡는다.
"""

from __future__ import annotations

from typing import Protocol


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
