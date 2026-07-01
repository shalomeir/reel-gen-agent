"""execute 산출물 폴더와 RunManifest를 잡는 헬퍼.

execute는 폴더를 만들거나 이름 짓지 않는다. 주어진 ReelProfile이 들어 있는 폴더가
곧 outputs/<run_id>/ 이고, run_id는 그 폴더 이름이다(plan-stage가 만든 규약).
"""

from __future__ import annotations

from pathlib import Path

from .schema import ReelProfile, RunManifest


def plan_dir_for(profile_path: str) -> Path:
    """ReelProfile json과 plan 산출물(캐릭터·제품·스틸 콘티)이 든 폴더 = outputs/<run>/plan/."""
    return Path(profile_path).parent


def output_dir_for(profile_path: str) -> Path:
    """run 루트(= outputs/<run>/)를 돌려준다. 결과물 3종(final/report/upload)이 여기 떨어진다.

    새 레이아웃은 ReelProfile이 outputs/<run>/plan/ 안에 있으므로 그 부모가 run 루트다.
    구 레이아웃(ReelProfile이 run 루트에 바로 있음)도 그대로 지원한다(하위호환).
    """
    plan_dir = Path(profile_path).parent
    return plan_dir.parent if plan_dir.name == "plan" else plan_dir


def new_manifest(profile_path: str, profile: ReelProfile) -> RunManifest:
    """폴더 이름을 run_id로 쓰는 빈 RunManifest를 만든다."""
    return RunManifest(run_id=output_dir_for(profile_path).name, input_path=profile_path)
