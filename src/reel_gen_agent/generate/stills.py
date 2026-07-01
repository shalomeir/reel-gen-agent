"""패널 스틸 보장: still_image가 없는 패널을 채운다(execute 진입 전).

컷별 프롬프트 + 잠근 캐릭터/제품 이미지를 reference로 나노바나나 스틸을 만든다. 생성이
실패하거나 클라이언트가 없으면 잠금(product_lock/subject_lock)에 맞는 에셋 이미지를 그대로
스틸로 재사용해, 키가 없어도 파이프라인이 끝까지 돌게 한다(워킹 스켈레톤 원칙).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .image_client import ImageClient
from .schema import ReelProfile


def _panel_refs(panel, character_image: str | None, product_image: str | None) -> list[str]:
    """이 패널이 참조할 에셋 이미지 목록. 잠금 플래그를 따른다."""
    refs: list[str] = []
    if panel.subject_lock and character_image:
        refs.append(character_image)
    if panel.product_lock and product_image:
        refs.append(product_image)
    # 아무 잠금도 없으면 최소한 캐릭터를 일관성 기준으로 넣는다.
    if not refs:
        refs = [r for r in (character_image, product_image) if r]
    return refs


def _fallback_still(panel, character_image: str | None, product_image: str | None) -> str | None:
    """생성 실패 시 재사용할 에셋 이미지. 제품 컷이면 제품, 아니면 캐릭터."""
    if panel.product_lock and product_image:
        return product_image
    if character_image:
        return character_image
    return product_image


def ensure_panel_stills(
    profile: ReelProfile,
    out_dir: str,
    image_client: ImageClient | None,
    character_image: str | None,
    product_image: str | None,
) -> int:
    """still_image가 없는 패널을 채운다. 채운(또는 폴백한) 패널 수를 반환한다."""
    panels = profile.storyboard.panels
    missing = [p for p in panels if not p.still_image]
    if not missing:
        return 0

    panels_dir = Path(out_dir) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    filled = 0
    for panel in missing:
        refs = _panel_refs(panel, character_image, product_image)
        prompt = panel.prompt or profile.storyboard.global_prompt or profile.product.name
        out = str(panels_dir / f"still_{panel.index}.png")
        generated = False
        if image_client is not None:
            try:
                # 컷 start 스틸은 영상 생성 reference로 주입되므로 히어로(4K Pro)로 만든다.
                panel.still_image = image_client.generate(prompt, refs, out, hero=True)
                generated = True
            except Exception:
                generated = False
        if not generated:
            fallback = _fallback_still(panel, character_image, product_image)
            if fallback and Path(fallback).exists():
                dst = str(panels_dir / f"still_{panel.index}{Path(fallback).suffix}")
                shutil.copy2(fallback, dst)
                panel.still_image = dst
        if panel.still_image:
            filled += 1
    return filled
