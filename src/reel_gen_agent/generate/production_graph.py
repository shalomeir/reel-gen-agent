"""execute 오케스트레이터(워킹 스켈레톤). 그래프 위상은 정적, 라우팅은 데이터 기반.

흐름: load -> production_plan -> materials -> assemble -> verify -> describe -> evaluate -> report.
지금은 순차 함수다. LangGraph 노드/Send 팬아웃/verify 리페어 루프는 Milestone 2에서 얹는다.
"""

from __future__ import annotations

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


def run_production(profile_path: str, *, use_vlm: bool = True) -> RunManifest:
    profile = ReelProfile.model_validate_json(Path(profile_path).read_text(encoding="utf-8"))
    out_dir = output_dir_for(profile_path)
    manifest = new_manifest(profile_path, profile)

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
