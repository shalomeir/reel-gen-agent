"""profile_assembly 노드: 기획 부산물을 ReelProfile로 동결하고 파일로 쓴다.

같은 ReelProfile은 유사 영상을 만든다(execute의 입력). 파일명은 run_paths 규약을 따른다.
"""

from __future__ import annotations

from pathlib import Path

from .run_paths import profile_filename
from .schema import (
    AssetBible,
    InputMeta,
    ModelSpec,
    MusicSpec,
    NarrationSpec,
    Objective,
    ProductSpec,
    Provenance,
    ReelProfile,
    Storyboard,
    StyleDimensions,
)


def assemble_profile(parts: dict) -> ReelProfile:
    objective: Objective = parts["objective"]
    product: ProductSpec = parts["product"]
    return ReelProfile(
        objective=objective,
        product=product,
        # meta는 스토리보드가 쓴 것과 같아야 한다(길이·fps 정렬). 빠지면 프로필 meta가 기본
        # 14초로 남아 스토리보드(레퍼런스 길이)와 어긋난다.
        meta=parts.get("meta") or InputMeta(),
        character=parts.get("character") or ModelSpec(),
        style=parts.get("style") or StyleDimensions(),
        narrative_arc=parts.get("narrative_arc", []),
        asset_bible=parts.get("asset_bible") or AssetBible(),
        storyboard=parts.get("storyboard") or Storyboard(),
        narration=parts.get("narration") or NarrationSpec(),
        music=parts.get("music") or MusicSpec(),
        provenance=parts.get("provenance") or Provenance(),
    )


def write_profile(profile: ReelProfile, out_dir: Path, run_id: str) -> Path:
    path = Path(out_dir) / profile_filename(run_id)
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return path
