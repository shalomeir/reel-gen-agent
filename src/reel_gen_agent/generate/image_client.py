"""이미지 생성 클라이언트 인터페이스. 백엔드는 Nano Banana(Gemini 네이티브 이미지) 단일 경로다.

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
# 히어로 스틸(인물, 캐릭터 설정 샷, 제품 카탈로그, 컷 start/reference 이미지)은 Nano Banana
# Pro로 승격한다(ai-model-records.md §3 히어로 이미지 팁). 인물 표현이 특히 여기서 좋아진다.
DEFAULT_HERO_IMAGE_MODEL = "gemini-3.1-pro-image-preview"

# 히어로 스틸 상수(ai-model-records.md §3). 기본 동작은 Pro 모델로 4K(9:16) 생성 후 원본
# 그대로 저장이다. 처음부터 1080x1920으로 뽑지 않는 이유는 고해상도 생성물의 얼굴·피부·제품
# 디테일이 더 살기 때문이다. 아래 TARGET/SHARPNESS/CONTRAST/JPEG 값은 최종 1080x1920 배포
# 프레임이 꼭 필요할 때만 쓰는 옵션 마감 레시피(fit_delivery_frame)에 쓴다.
HERO_IMAGE_SIZE = "4K"
HERO_TARGET_W = 1080
HERO_TARGET_H = 1920
HERO_SHARPNESS = 1.16
HERO_CONTRAST = 1.04
HERO_JPEG_QUALITY = 97


class ImageClient(Protocol):
    def generate(self, prompt: str, refs: list[str], out_path: str, hero: bool = False) -> str:
        """프롬프트와 reference 이미지들로 이미지를 만들어 out_path에 저장하고 경로를 돌려준다.

        hero=True면 인물·캐릭터 설정 샷·제품 카탈로그·컷 start(영상 reference) 같은 고품질
        스틸로 보고, 고해상도 생성 + 다운스케일 후처리 경로를 탄다(ai-model-records.md §3).
        """
        ...


class StubImageClient:
    """정해 둔 경로에 빈 파일을 쓰는 테스트용 클라이언트(외부 호출 없음)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], str, bool]] = []

    def generate(self, prompt: str, refs: list[str], out_path: str, hero: bool = False) -> str:
        self.calls.append((prompt, refs, out_path, hero))
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("stub-image")
        return out_path


class NanoBananaImageClient:
    """Gemini 이미지(나노바나나) 실제 백엔드. 캐릭터·제품 reference로 일관성을 잡는다.

    모델은 .env `GEMINI_IMAGE_MODEL`(기본 gemini-3.1-flash-image-preview). 백엔드/응답
    모달리티 조합을 차례로 시도하고, 끝까지 이미지를 못 얻으면 RuntimeError를 던져 호출
    측이 폴백(에셋 이미지 재사용)하게 한다.
    """

    def __init__(self, model: str | None = None, hero_model: str | None = None) -> None:
        self.model = model or os.environ.get("GEMINI_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL
        # 히어로 스틸은 Pro급으로 승격하되, 키/백엔드가 못 받으면 기본 모델로 폴백한다.
        self.hero_model = (
            hero_model or os.environ.get("GEMINI_IMAGE_MODEL_HERO") or DEFAULT_HERO_IMAGE_MODEL
        )

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

    def _attempts(self, hero: bool) -> list[tuple[str, object]]:
        """(모델, config) 시도 순서. 히어로면 Pro+4K를 먼저 쓰고 기본 모델로 폴백한다."""
        from google.genai import types

        if hero:
            img_cfg = types.ImageConfig(aspect_ratio="9:16", image_size=HERO_IMAGE_SIZE)
            return [
                (self.hero_model, types.GenerateContentConfig(
                    response_modalities=["IMAGE"], image_config=img_cfg)),
                (self.hero_model, types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"], image_config=img_cfg)),
                # Pro/4K를 못 받는 키·백엔드를 위한 폴백(기본 모델, 컨트롤 없이).
                (self.model, types.GenerateContentConfig(response_modalities=["IMAGE"])),
                (self.model, None),
            ]
        # 이미지 모델은 기본이 이미지 응답이지만, 일부는 response_modalities 명시가 필요하다.
        return [
            (self.model, None),
            (self.model, types.GenerateContentConfig(response_modalities=["IMAGE"])),
            (self.model, types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])),
        ]

    def generate(self, prompt: str, refs: list[str], out_path: str, hero: bool = False) -> str:
        from google.genai import types

        contents: list = []
        for ref in refs:
            if ref and os.path.exists(ref):
                with open(ref, "rb") as fh:
                    contents.append(types.Part.from_bytes(data=fh.read(), mime_type="image/jpeg"))
        contents.append(prompt)

        attempts = self._attempts(hero)
        for selection in self._selections():
            try:
                client = make_client(selection)
            except Exception:
                continue
            for model, config in attempts:
                try:
                    kwargs: dict[str, object] = {"model": model, "contents": contents}
                    if config is not None:
                        kwargs["config"] = config
                    response = client.models.generate_content(**kwargs)
                except Exception:
                    continue
                data = self._extract_bytes(response)
                if data:
                    # 히어로도 4K 원본을 그대로 저장한다. 리사이즈/크롭은 하지 않는다
                    # (asset/reference/컷 start용 4K는 native로 두는 편이 낫다,
                    # ai-model-records.md §3). PNG로 정규화해 ffmpeg 입력을 안정화한다.
                    import io

                    from PIL import Image

                    Image.open(io.BytesIO(data)).convert("RGB").save(out_path)
                    return out_path
        raise RuntimeError("nano banana 이미지 생성 실패(모든 백엔드/모달리티)")


def fit_delivery_frame(
    src_path: str,
    out_path: str,
    width: int = HERO_TARGET_W,
    height: int = HERO_TARGET_H,
) -> str:
    """4K 히어로 스틸을 최종 배포 프레임(기본 1080x1920)으로 마감한다.

    필요할 때만 쓰는 옵션 마감 레시피다(ai-model-records.md §3). 가로세로를 채우도록
    스케일 후 센터크롭하고, 선명·대비를 살짝 올린다. JPEG 확장자면 quality=97로 저장한다.
    기본 4K 자산은 native로 두므로 컷 start/reference에는 호출하지 않는다.
    """
    from PIL import Image, ImageEnhance

    img = Image.open(src_path).convert("RGB")
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    img = img.resize((round(src_w * scale), round(src_h * scale)), Image.Resampling.LANCZOS)
    left = (img.width - width) // 2
    top = (img.height - height) // 2
    img = img.crop((left, top, left + width, top + height))
    img = ImageEnhance.Sharpness(img).enhance(HERO_SHARPNESS)
    img = ImageEnhance.Contrast(img).enhance(HERO_CONTRAST)
    if out_path.lower().endswith((".jpg", ".jpeg")):
        img.save(out_path, quality=HERO_JPEG_QUALITY)
    else:
        img.save(out_path)
    return out_path
