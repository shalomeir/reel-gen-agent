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
    # 크리에이터는 한 사람 제품 영상에서 거의 모든 컷에 나온다. 그래서 캐릭터 이미지를 컷 종류와
    # 무관하게 '항상' 일관성 기준으로 넣는다. 예전엔 subject_lock 컷에만 넣어서, 제품 강조 컷
    # (product_lock)의 인물이 캐릭터 레퍼런스 없이 생성돼 컷마다 다른 인종/얼굴로 드리프트했다
    # (한 영상에 흑인·백인이 섞이는 버그). 제품 컷이면 제품 이미지도 함께 참조로 넣는다.
    if character_image:
        refs.append(character_image)
    if panel.product_lock and product_image:
        refs.append(product_image)
    # 캐릭터가 아예 없을 때만 제품이라도 넣는다.
    if not refs and product_image:
        refs.append(product_image)
    # 대표 key_visual은 이 컷의 앵커 자신이 아닌 한 룩 일관성 레퍼런스로 얹는다.
    if key_visual and key_visual != panel.still_image and key_visual not in refs:
        refs.append(key_visual)
    return refs


def _fallback_still(
    panel,
    character_image: str | None,
    product_image: str | None,
    key_visual: str | None = None,
    person_forward: bool = False,
) -> str | None:
    """생성 실패 시 재사용할 에셋 이미지.

    person_forward(세그먼트 앵커)면 인물을 최우선으로 돌려준다: 세그먼트 시작 프레임이 곧
    그 세그먼트 인물이라, 여기서 제품 패키지샷이 오면 세그먼트가 인물 없이 제품만으로 시작해
    인물 통일이 깨진다(같은 사람 유지가 최우선). key_visual(인물 대표 프레임) -> 캐릭터 순.
    일반(비앵커) 컷은 기존대로 제품 컷이면 제품을 재사용한다.
    """
    if person_forward:
        return key_visual or character_image or product_image
    if panel.product_lock and product_image:
        return product_image
    if character_image:
        return character_image
    return product_image


# key_visual(인물이 드러난 대표 프레임)을 '정체성 base'로 쓴다. i2v는 세그먼트마다 앵커 스틸에서
# 독립 시작하므로, 앵커들이 같은 사람이 아니면 세그먼트 간 인물이 갈린다(흑인·백인 섞임). 그래서
# key_visual과 '같은 사람·같은 룩'을 유지하고 이 컷의 샷/동작만 바꾸라고 못 박는다 — 즉 모든
# 앵커가 하나의 key_visual을 살짝 변형한 것이 되어 인물이 일관된다(사용자 지시: veo i2v에서도 필수).
_KEY_VISUAL_VIBE = (
    "Use the provided key reference frame as the identity and style base: keep the SAME person "
    "(same face, ethnicity, skin tone, hair, age), the same styling and the same lighting/color "
    "mood as that frame. Change ONLY the camera framing and the action for this specific cut. "
    "The creator's face must be clearly visible."
)

# 캐릭터 레퍼런스가 있을 때, 컷마다 같은 사람을 유지하도록 못 박는다. 스틸은 컷별 영상의 시작
# 프레임이라, 여기서 인물이 바뀌면 영상도 인물이 바뀐다(한 영상에 다른 인종/얼굴이 섞이는 걸 방지).
_CHARACTER_LOCK = (
    "The person is the SAME individual as the provided character reference image — keep the same "
    "face, ethnicity, skin tone, hair and age across every shot. Never change the person."
)


def ensure_panel_stills(
    profile: ReelProfile,
    out_dir: str,
    image_client: ImageClient | None,
    character_image: str | None,
    product_image: str | None,
    anchor_indices: set[int] | None = None,
    key_visual: str | None = None,
    hero: bool = True,
) -> int:
    """still_image가 없는 패널을 채운다. 채운(또는 폴백한) 패널 수를 반환한다.

    anchor_indices가 주어지면 그 패널만 채운다(멀티샷 세그먼트 경로: 세그먼트당 앵커 1장만
    생성해 컷마다 이미지를 만들지 않는다). None이면 전 패널을 채운다(ken_burns 폴백).
    key_visual이 있으면 캐릭터·제품과 함께 모든 컷 생성의 레퍼런스로 넣어 바이브(조명·색)를 맞춘다.

    hero=True면 컷 start 스틸을 4K Pro로 만든다(영상 모델 reference로 주입되므로 고품질 필요).
    ken_burns는 로컬 팬/줌 베이스라 4K Pro가 낭비이므로 hero=False(Flash)로 부른다.
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
    # 세그먼트 앵커(시작 프레임)를 채우는 호출이면 인물 우선으로 간다. 앵커는 그 세그먼트의 인물을
    # 정하는 프레임이라, 제품 컷이어도 사람이 주체로 있어야 세그먼트끼리 인물이 통일된다. 제품
    # 패키지샷으로 시작하면(생성 실패 폴백 등) 그 세그먼트가 인물 없이 제품만으로 시작해 개판이 된다.
    person_forward = anchor_indices is not None
    filled = 0
    for panel in missing:
        refs = _panel_refs(panel, character_image, product_image, key_visual)
        base = panel.prompt or profile.storyboard.global_prompt or profile.product.name
        vibe = f" {_KEY_VISUAL_VIBE}" if (key_visual and key_visual != panel.still_image) else ""
        # image-to-video 시작 프레임이므로 반드시 단일 순간이어야 한다. 콘티/훅이 여러 동작을
        # 묘사해도 스틸은 그 첫 순간 하나만 그린다(콜라주·스토리보드·그리드·분할·연속 패널 금지).
        # reference-to-video가 아닌 한 콜라주 스틸을 그대로 넣으면 영상이 콜라주로 시작한다.
        from .product import SOLO_PERSON

        # 캐릭터 이미지가 참조에 들어가면 '같은 사람 유지'를 명시해 컷 간 인물 드리프트를 막는다.
        char_lock = f" {_CHARACTER_LOCK}" if character_image else ""
        # 앵커는 사람이 주체임을 못 박아 제품만 있는 패키지샷으로 시작하지 않게 한다(제품은 손에
        # 들거나 곁에 두는 소품이지 화면 전체를 채우는 주체가 아니다).
        anchor_person = (
            " The creator (a real person) is the main subject filling the frame; if the product "
            "appears, it is held or beside them, never a product-only packshot with no person."
            if person_forward
            else ""
        )
        prompt = f"{base}. {_SINGLE_MOMENT_RULE} {SOLO_PERSON}{char_lock}{anchor_person}{vibe}"
        out = str(panels_dir / f"still_{panel.index}.png")
        generated = False
        if image_client is not None:
            try:
                # i2v면 컷 start가 영상 reference라 히어로(4K Pro), ken_burns면 로컬 베이스라 Flash.
                panel.still_image = image_client.generate(prompt, refs, out, hero=hero)
                generated = True
            except Exception:
                generated = False
        if not generated:
            fallback = _fallback_still(
                panel, character_image, product_image, key_visual, person_forward
            )
            if fallback and Path(fallback).exists():
                dst = str(panels_dir / f"still_{panel.index}{Path(fallback).suffix}")
                shutil.copy2(fallback, dst)
                panel.still_image = dst
        if panel.still_image:
            filled += 1
    return filled
