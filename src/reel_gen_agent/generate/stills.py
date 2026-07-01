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

# 스틸은 image-to-video의 시작 프레임이다 -> 단일 순간 강제(콜라주/스토리보드 스틸 금지 rule).
_SINGLE_MOMENT_RULE = (
    "This is a single photographic instant, the first frame of one video shot. Show exactly one "
    "moment: NOT a collage, storyboard, grid, split-screen, filmstrip, before/after, or multiple "
    "panels/moments in one image. One clean full-frame photo."
)


def _panel_refs(
    panel,
    character_image: str | None,
    product_image: str | None,
    key_visual: str | None = None,
) -> list[str]:
    """이 패널이 참조할 에셋 이미지 목록. 잠금 플래그를 따른다.

    key_visual(영상 대표 프레임)이 있으면 모든 컷에 함께 넣어 전체 스틸이 같은 룩·분위기로
    이어지게 한다(중간만 쓰면 결이 튀므로 전 컷 일관성 기준으로 주입).
    """
    refs: list[str] = []
    if panel.subject_lock and character_image:
        refs.append(character_image)
    if panel.product_lock and product_image:
        refs.append(product_image)
    # 아무 잠금도 없으면 최소한 캐릭터를 일관성 기준으로 넣는다.
    if not refs:
        refs = [r for r in (character_image, product_image) if r]
    # 대표 key_visual은 이 컷의 앵커 자신이 아닌 한 룩 일관성 레퍼런스로 얹는다.
    if key_visual and key_visual != panel.still_image and key_visual not in refs:
        refs.append(key_visual)
    return refs


def _fallback_still(panel, character_image: str | None, product_image: str | None) -> str | None:
    """생성 실패 시 재사용할 에셋 이미지. 제품 컷이면 제품, 아니면 캐릭터."""
    if panel.product_lock and product_image:
        return product_image
    if character_image:
        return character_image
    return product_image


# key_visual이 refs에 있을 때 덧붙이는 지시. 합성/복제가 아니라 조명·색·분위기(바이브)를
# 맞추라고 명시해, 전 컷 스틸이 대표 프레임과 같은 결로 이어지게 한다(사용자 지시).
_KEY_VISUAL_VIBE = (
    "Match the overall lighting, color grade and mood/vibe of the provided key reference frame "
    "(use it for atmosphere and consistency, not to copy its exact composition)."
)


def ensure_panel_stills(
    profile: ReelProfile,
    out_dir: str,
    image_client: ImageClient | None,
    character_image: str | None,
    product_image: str | None,
    anchor_indices: set[int] | None = None,
    key_visual: str | None = None,
) -> int:
    """still_image가 없는 패널을 채운다. 채운(또는 폴백한) 패널 수를 반환한다.

    anchor_indices가 주어지면 그 패널만 채운다(멀티샷 세그먼트 경로: 세그먼트당 앵커 1장만
    생성해 컷마다 이미지를 만들지 않는다). None이면 전 패널을 채운다(ken_burns 폴백).
    key_visual이 있으면 캐릭터·제품과 함께 모든 컷 생성의 레퍼런스로 넣어 바이브(조명·색)를 맞춘다.
    """
    panels = profile.storyboard.panels
    missing = [
        p
        for p in panels
        if not p.still_image and (anchor_indices is None or p.index in anchor_indices)
    ]
    if not missing:
        return 0

    panels_dir = Path(out_dir) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    filled = 0
    for panel in missing:
        refs = _panel_refs(panel, character_image, product_image, key_visual)
        base = panel.prompt or profile.storyboard.global_prompt or profile.product.name
        vibe = f" {_KEY_VISUAL_VIBE}" if (key_visual and key_visual != panel.still_image) else ""
        # image-to-video 시작 프레임이므로 반드시 단일 순간이어야 한다. 콘티/훅이 여러 동작을
        # 묘사해도 스틸은 그 첫 순간 하나만 그린다(콜라주·스토리보드·그리드·분할·연속 패널 금지).
        # reference-to-video가 아닌 한 콜라주 스틸을 그대로 넣으면 영상이 콜라주로 시작한다.
        prompt = f"{base}. {_SINGLE_MOMENT_RULE}{vibe}"
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
