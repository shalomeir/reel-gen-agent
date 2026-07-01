"""plan 페이즈 진입점. LangGraph plan 그래프를 만들고 실행한다([plan_graph.py]).

흐름: intake -> reference_seed -> character -> environment -> music -> hook <-> storyboard
(핑퐁) -> narration -> assets -> write. 각 노드는 공유 상태(PlanState)를 읽고 부분 업데이트를
돌려주며, Tracer가 노드 span을 로컬 trace(+옵션 Langfuse)에 남긴다([trace.py]).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .asset_bible import build_key_visual
from .image_client import ImageClient
from .intake import intake
from .plan_graph import build_plan_graph
from .profile_assembly import assemble_profile, write_profile
from .replan_graph import build_replan_graph
from .run_paths import create_run_dir, make_run_id
from .schema import AssetBible, ReelProfile
from .text_client import TextClient
from .trace import Tracer


def run_planning(
    raw: str,
    outputs_root: str,
    *,
    text_client: TextClient | None = None,
    image_client: ImageClient | None = None,
    style_feedback: str = "",
) -> Path:
    """입력 -> ReelProfile(plan/ 하위 JSON). plan 그래프를 컴파일해 한 번 실행한다(한 번에 밀기).

    style_feedback이 있으면(유사도 루프의 재계획) 스토리보드 등에 레퍼런스 정합 지시로 반영한다.
    HITL/게이트는 없다(run 방식으로 입력→ReelProfile→production 일괄, 확인 단계 없음).
    """
    result = intake(raw)
    if result.objective is None:
        raise ValueError("objective(영상 목적)는 필수다. 입력이 비었다.")

    # run_id는 출력 폴더 이름이자 trace run_id다(한 번만 만들어 재사용). 단독 명령은 session=run.
    run_id = make_run_id(result.objective.goal)
    tracer = Tracer(session_id=run_id, run_id=run_id)

    graph = build_plan_graph()
    final = graph.invoke(
        {
            "raw": raw,
            "outputs_root": outputs_root,
            "text_client": text_client,
            "image_client": image_client,
            "tracer": tracer,
            "style_feedback": style_feedback,
        }
    )
    return Path(final["profile_path"])


def _copy_identity_assets(bible: AssetBible, src_dir: Path, dst_dir: Path) -> None:
    """정체성 에셋 이미지 파일(캐릭터·제품·환경)을 원본 plan 폴더에서 새 폴더로 복사한다.

    key_visual은 여기서 복사하지 않는다(새 훅에 맞춰 재생성하거나, 실패 시 폴백에서 복사).
    파일이 없으면 조용히 건너뛴다(상대 파일명은 그대로라 새 프로필에서 해소된다).
    """
    names: list[str | None] = [
        bible.character.sheet_image,
        bible.character.key_shot_image,
        bible.product.sheet_image,
        bible.product.hero_image,
        bible.environment.reference_image,
    ]
    names += [v.image for v in bible.character.views]
    names += [v.image for v in bible.product.views]
    for rel in names:
        if not rel:
            continue
        src = src_dir / rel
        if src.exists():
            shutil.copy2(src, dst_dir / rel)


def run_replan(
    profile_path: str,
    outputs_root: str,
    *,
    text_client: TextClient | None = None,
    image_client: ImageClient | None = None,
) -> Path:
    """기존 ReelProfile을 새 훅으로 재전개해 새 폴더에 새 ReelProfile을 쓴다(specs/replan.md).

    정체성(objective/product/character/meta + 캐릭터·제품·환경 에셋)은 고정하고, narrative
    (hook<->storyboard, narration, music)만 다시 만든다. key_visual은 새 훅에 맞춰 재생성하되
    image_client가 없거나 실패하면 원본을 복사해 폴백한다. 산출 폴더는 새 훅 키워드로 명명한다.
    """
    src_profile = ReelProfile.model_validate_json(Path(profile_path).read_text(encoding="utf-8"))
    src_plan_dir = Path(profile_path).parent

    # narrative 노드가 쓰는 값만 원본에서 시딩한다(정체성은 그래프가 건드리지 않는다).
    # style/music은 복사본을 넘겨 원본 객체를 변형하지 않는다(hook 노드가 style.hook을 갈아끼운다).
    seed_run = make_run_id(src_profile.objective.goal)
    state = {
        "text_client": text_client,
        "image_client": None,  # 그래프는 이미지 작업을 하지 않는다.
        "tracer": Tracer(session_id=seed_run, run_id=seed_run),
        "objective": src_profile.objective,
        "product": src_profile.product,
        "meta": src_profile.meta,
        "character": src_profile.character,
        "environment": src_profile.asset_bible.environment,
        "style": src_profile.style.model_copy(deep=True),
        "music": src_profile.music.model_copy(deep=True),
        "delivery": src_profile.narration.delivery,
        "ref_voice_tone": src_profile.narration.voice.tone or "",
        "ref_voice_pace": src_profile.narration.voice.pace or "",
        "ref_hook": None,  # 새 아이디어: 레퍼런스 훅 오버레이를 끈다.
        "cut_count": len(src_profile.storyboard.panels),
        "hook_attempts": 0,
        "hook_feedback": "",
        "style_feedback": "",
    }
    final = build_replan_graph().invoke(state)

    # 새 훅 헤드라인으로 폴더를 명명한다(없으면 목적).
    new_hook = final["style"].hook
    keyword = getattr(new_hook, "headline", None) or src_profile.objective.goal
    new_run_id = make_run_id(keyword)
    new_plan_dir = create_run_dir(outputs_root, new_run_id) / "plan"
    new_plan_dir.mkdir(parents=True, exist_ok=True)

    # 정체성 에셋을 복사하고 asset_bible을 재사용(같은 상대 파일명 -> 새 폴더에서 해소).
    _copy_identity_assets(src_profile.asset_bible, src_plan_dir, new_plan_dir)
    asset_bible = src_profile.asset_bible.model_copy(deep=True)

    provenance = src_profile.provenance.model_copy(deep=True)
    provenance.seeds = {**provenance.seeds, "replanned_from": profile_path}

    new_profile = assemble_profile(
        {
            "objective": src_profile.objective,
            "product": src_profile.product,
            "meta": src_profile.meta,
            "character": src_profile.character,
            "style": final["style"],
            "narrative_arc": final.get("narrative_arc", []),
            "asset_bible": asset_bible,
            "storyboard": final["storyboard"],
            "narration": final["narration"],
            "music": final["music"],
            "provenance": provenance,
        }
    )

    # key_visual 재생성: 복사한 캐릭터·제품 참조로 새 커버를 그린다. 실패/부재 시 원본 복사 폴백.
    char_rel = asset_bible.character.key_shot_image
    prod_rel = asset_bible.product.hero_image
    char_ref = str(new_plan_dir / char_rel) if char_rel else None
    prod_ref = str(new_plan_dir / prod_rel) if prod_rel else None
    kv = build_key_visual(new_profile, image_client, str(new_plan_dir), char_ref, prod_ref)
    if kv:
        asset_bible.key_visual = kv
    elif src_profile.asset_bible.key_visual:  # 폴백: 원본 커버를 복사해 재사용
        old_kv = src_plan_dir / src_profile.asset_bible.key_visual
        if old_kv.exists():
            shutil.copy2(old_kv, new_plan_dir / src_profile.asset_bible.key_visual)
        asset_bible.key_visual = src_profile.asset_bible.key_visual

    return write_profile(new_profile, new_plan_dir, new_run_id)
