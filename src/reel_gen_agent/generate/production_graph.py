"""execute 오케스트레이터(워킹 스켈레톤). 그래프 위상은 정적, 라우팅은 데이터 기반.

흐름: load -> production_plan -> materials -> assemble -> verify -> describe -> evaluate -> report.
지금은 순차 함수다. LangGraph 노드/Send 팬아웃/verify 리페어 루프는 Milestone 2에서 얹는다.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..analysis.rubric import evaluate_video
from .assemble import assemble
from .conformance import verify_conformance
from .describe import build_upload_kit, render_upload_md
from .materials import build_materials
from .production_plan import resolve_plan
from .report import build_final_report, render_report_md
from .run_context import new_manifest, output_dir_for
from .schema import NodeRun, ReelProfile, RunManifest
from .stills import ensure_panel_stills


def _resolve_asset(image: str | None, base_dir: Path) -> str | None:
    """ReelProfile에 상대 파일명으로 적힌 에셋 이미지를 절대 경로로 푼다."""
    if not image:
        return None
    p = Path(image)
    if not p.is_absolute():
        p = base_dir / p
    return str(p) if p.exists() else None


def run_production(profile_path: str, *, use_vlm: bool = True) -> RunManifest:
    profile = ReelProfile.model_validate_json(Path(profile_path).read_text(encoding="utf-8"))
    out_dir = output_dir_for(profile_path)
    manifest = new_manifest(profile_path, profile)

    # 스틸 보장: 패널에 still_image가 없으면 에셋을 reference로 생성(없으면 에셋 재사용).
    # 키가 필요한 생성 클라이언트는 채울 게 있을 때만 만든다(스틸이 다 있으면 건드리지 않음).
    if any(not p.still_image for p in profile.storyboard.panels):
        base_dir = Path(profile_path).resolve().parent
        char_img = _resolve_asset(profile.asset_bible.character.key_shot_image, base_dir)
        prod_img = _resolve_asset(profile.asset_bible.product.hero_image, base_dir)
        client = None
        if os.environ.get("REEL_STILLS", "gen").lower() != "off":
            try:
                from .image_client import NanoBananaImageClient

                client = NanoBananaImageClient()
            except Exception:
                client = None
        filled = ensure_panel_stills(profile, str(out_dir), client, char_img, prod_img)
        manifest.nodes.append(NodeRun(name="stills", artifacts=[]))
        if filled == 0:
            raise ValueError("stills: 채울 수 있는 패널 스틸이 없다(에셋 이미지 확인).")

    plan = resolve_plan(profile, env={})
    manifest.production_plan = plan
    manifest.nodes.append(NodeRun(name="production_plan"))

    materials = build_materials(profile, plan, str(out_dir))
    manifest.nodes.append(NodeRun(name="materials", artifacts=materials.shot_clips))

    final_video = str(out_dir / "final.mp4")
    assemble(materials, profile.meta, final_video)
    manifest.final_video = final_video
    manifest.panel_segments = materials.shot_clips
    manifest.nodes.append(NodeRun(name="assemble", artifacts=[final_video]))

    # 레퍼런스 없는 intrinsic 체크. VLM 지각 체크는 use_vlm일 때만(키 없으면 건너뛴다).
    conf = verify_conformance(final_video, use_vlm=use_vlm)
    conf_dump = conf.model_dump()
    manifest.nodes.append(NodeRun(name="verify"))

    kit = build_upload_kit(profile)
    render_upload_md(kit, str(out_dir / "upload.md"))
    manifest.nodes.append(NodeRun(name="describe", artifacts=[str(out_dir / "upload.md")]))

    rubric_dump: dict = {}
    if use_vlm:
        rubric_dump = evaluate_video(final_video).model_dump()
    manifest.nodes.append(NodeRun(name="evaluate"))

    # run_id는 항상 폴더 이름(str)으로 잡혀 있다(new_manifest). 리포트는 그 이름을 쓴다.
    report = build_final_report(out_dir.name, profile, manifest, conf_dump, rubric_dump)
    render_report_md(report, str(out_dir / "report.md"))
    manifest.nodes.append(NodeRun(name="report", artifacts=[str(out_dir / "report.md")]))

    (out_dir / "run.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest
