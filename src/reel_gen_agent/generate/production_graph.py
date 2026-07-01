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
from .run_context import new_manifest, output_dir_for, plan_dir_for
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
    out_dir = output_dir_for(profile_path)  # run 루트: 결과물 3종이 여기 떨어진다
    plan_dir = plan_dir_for(profile_path)  # plan 산출물(스틸 콘티)은 여기 둔다
    render_dir = out_dir / "render"  # execute 작업 파일(클립·오디오): 재실행마다 다시 만든다
    manifest = new_manifest(profile_path, profile)

    # 실제 환경(GOOGLE_CLOUD_PROJECT/FAL_KEY 등)을 넘겨야 영상 백엔드가 선택된다.
    # 빈 dict를 넘기면 항상 ken_burns로 폴백해 실 영상 생성이 꺼진다. 세그먼트를 먼저 알아야
    # 앵커 스틸만 만들 수 있으므로 스틸 보장보다 먼저 계획을 세운다.
    plan = resolve_plan(profile, env=dict(os.environ))
    manifest.production_plan = plan
    manifest.nodes.append(NodeRun(name="production_plan"))

    # 스틸 보장: 세그먼트 앵커(첫 패널)만 생성한다([multishot-segments.md]). 멀티샷 경로는
    # 컷마다 이미지를 만들지 않고, 앵커 1장 + 샷 리스트 프롬프트로 모델이 내부 컷을 만든다.
    # ken_burns는 패널마다 세그먼트 1개라 사실상 전 패널이 앵커다(컷당 줌 유지).
    anchor_indices = {seg[0] for seg in plan.segments if seg}
    if any(not p.still_image for p in profile.storyboard.panels if p.index in anchor_indices):
        base_dir = plan_dir.resolve()  # 캐릭터·제품 에셋은 plan/ 안에 있다
        char_img = _resolve_asset(profile.asset_bible.character.key_shot_image, base_dir)
        prod_img = _resolve_asset(profile.asset_bible.product.hero_image, base_dir)
        client = None
        if os.environ.get("REEL_STILLS", "gen").lower() != "off":
            try:
                from .image_client import NanoBananaImageClient

                client = NanoBananaImageClient()
            except Exception:
                client = None
        # 스틸(콘티)은 plan/ 하위에 만들어 plan 산출물로 남긴다.
        filled = ensure_panel_stills(
            profile, str(plan_dir), client, char_img, prod_img, anchor_indices=anchor_indices
        )
        manifest.nodes.append(NodeRun(name="stills", artifacts=[]))
        if filled == 0:
            raise ValueError("stills: 채울 수 있는 앵커 스틸이 없다(에셋 이미지 확인).")
        # 생성한 스틸 경로를 plan ReelProfile에 되써, 재실행(execute만) 시 나노바나나 재호출
        # 없이 같은 plan으로 결과를 다시 만든다(재실행 저비용).
        Path(profile_path).write_text(
            profile.model_dump_json(indent=2), encoding="utf-8"
        )

    materials = build_materials(profile, plan, str(render_dir))
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
