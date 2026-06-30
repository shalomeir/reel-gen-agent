"""execute 산출물 폴더와 RunManifest를 잡는 헬퍼.

execute는 폴더를 만들거나 이름 짓지 않는다. 주어진 ReelProfile이 들어 있는 폴더가
곧 outputs/<run_id>/ 이고, run_id는 그 폴더 이름이다(plan-stage가 만든 규약).
"""

from __future__ import annotations

from pathlib import Path

from .schema import ReelProfile, RunManifest


def output_dir_for(profile_path: str) -> Path:
    """ReelProfile json이 들어 있는 폴더(= outputs/<run_id>/)를 돌려준다."""
    return Path(profile_path).parent


def new_manifest(profile_path: str, profile: ReelProfile) -> RunManifest:
    """폴더 이름을 run_id로 쓰는 빈 RunManifest를 만든다."""
    return RunManifest(run_id=output_dir_for(profile_path).name, input_path=profile_path)
