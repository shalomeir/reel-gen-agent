"""report 노드: 회차 종합 리포트(FinalReport -> report.md).

레이아웃: 유저 입력(앞단) -> 의견 -> 노드 흐름 -> 모델 -> bgm -> eval -> 예측 ->
노드별 프롬프트(뒤). 렌더링은 결정론, final_opinion/viral_prediction만 LLM(여기선 빈값).
"""

from __future__ import annotations

import os

from .cost import (
    _bgm_model,
    _effective_video_model,
    _text_key_present,
    _tts_model,
    estimate_cost,
)
from .schema import (
    BgmReport,
    CostReport,
    FinalReport,
    NodePrompt,
    ReelProfile,
    RunManifest,
    UserInputEcho,
)


def _character_summary(profile: ReelProfile) -> dict:
    """캐릭터 설정(ModelSpec)을 report용 dict로. 빈 값은 뺀다."""
    c = profile.character
    fields = {
        "name": c.name,
        "age": c.age,
        "gender": c.gender,
        "look": c.look,
        "body": c.body,
        "wardrobe": c.wardrobe,
    }
    return {k: v for k, v in fields.items() if v}


def _style_summary(profile: ReelProfile) -> dict:
    s = profile.style
    out: dict = {}
    if s.tone:
        out["tone"] = ", ".join(s.tone)
    if s.pacing:
        out["pacing"] = s.pacing
    if s.motion:
        out["motion"] = s.motion
    if s.palette:
        out["palette"] = ", ".join(s.palette)
    return out


def _hook_summary(profile: ReelProfile) -> dict:
    h = profile.style.hook
    if not h:
        return {}
    fields = {
        "type": h.hook_type,
        "headline": h.headline,
        "bottom_caption": h.bottom_caption,
        "visual": h.visual_direction,
    }
    return {k: v for k, v in fields.items() if v}


def _storyboard_summary(profile: ReelProfile) -> list:
    """컷별 요약: 타임코드 + beat + 자막 + 행동."""
    rows = []
    for p in profile.storyboard.panels:
        rows.append(
            {
                "t": f"{int(p.t_start or 0) // 60:02d}:{int(p.t_start or 0) % 60:02d}",
                "beat": p.beat or "",
                "subtitle": p.subtitle_text or "",
                "action": p.action or "",
            }
        )
    return rows


def _bgm_report(profile: ReelProfile, plan, env: dict) -> BgmReport:
    """BGM을 'gen'이 아니라 실제 모델 + 음악 의도로 보고한다."""
    kind = plan.bgm if plan else "none"
    model = _bgm_model(plan, env)  # "lyria-002" / "synth" / "none"
    label = {"synth": "합성(폴백)", "none": None}.get(model, model)
    m = profile.music
    bits = [
        m.mood and f"무드 {m.mood}",
        (m.style or m.type) and f"장르 {m.style or m.type}",
        m.tempo and f"템포 {m.tempo}",
        m.instrumentation and f"악기 {m.instrumentation}",
        m.prominence and f"존재감 {m.prominence}",
    ]
    desc = ", ".join(b for b in bits if b) or None
    return BgmReport(kind=kind, model=label, description=desc)


def _video_used_str(manifest: RunManifest, plan, env: dict) -> str | None:
    """실제로 영상을 만든 백엔드를 사람이 읽을 문자열로. '선택'이 아니라 '실행'을 말한다.

    런타임에 영상 모델이 세그먼트에 실패하면 그 컷은 ken_burns로 폴백하므로, 전량/부분
    폴백을 그대로 드러낸다. 구버전 매니페스트(기록 없음)면 plan 기준으로 폴백 표기한다.
    """
    backend = manifest.video_backend_used
    if not backend:  # 실행 기록이 없는 회차 -> plan에서 유효 모델을 추정
        return _effective_video_model(plan, env) if plan else None
    if backend == "ken_burns":
        return "ken_burns"
    total = manifest.video_segments_total
    fb = manifest.video_segments_fallback
    if total and fb >= total:
        return f"ken_burns (계획: {backend}, 전량 폴백)"
    if fb > 0:
        return f"{backend} ({total - fb}/{total} 컷, {fb}컷 ken_burns 폴백)"
    return backend


def _models_used(manifest: RunManifest, plan, env: dict) -> dict:
    """리포트 '사용 모델' 섹션. 영상은 실제 렌더 결과, 나머지는 용도별 실제 백엔드로 채운다."""
    models: dict = {}
    video = _video_used_str(manifest, plan, env)
    if video:
        models["video"] = video
    if plan:
        hero = env.get("GEMINI_IMAGE_MODEL_HERO") or "gemini-3.1-pro-image-preview"
        flash = env.get("GEMINI_IMAGE_MODEL") or "gemini-3.1-flash-image-preview"
        # ken_burns 스틸은 Flash, i2v 앵커 스틸은 히어로 4K(stills 노드·cost와 같은 규칙).
        stills_kb = _effective_video_model(plan, env) == "ken_burns"
        models["image_still"] = flash if stills_kb else hero
        models["image_asset"] = hero  # 캐릭터·제품·패키지·키비주얼은 항상 히어로 4K
        models["bgm"] = _bgm_model(plan, env)  # lyria-* / synth / none
        if plan.voice_strategy == "separate_tts":
            models["tts"] = _tts_model(plan, env)  # eleven_v3 / gemini tts
    if _text_key_present(env):
        models["llm"] = env.get("GEMINI_TEXT_MODEL") or "gemini-3.1-pro-preview"
    return models


def build_final_report(
    run_id: str,
    profile: ReelProfile,
    manifest: RunManifest,
    conformance: dict,
    rubric: dict,
    repair: dict | None = None,
) -> FinalReport:
    echo = UserInputEcho(
        objective=profile.objective.goal,
        product_input=profile.product.name,
        reference_ref=profile.provenance.reference_ref,
    )
    prompts = [NodePrompt(node=nr.name, prompt=nr.prompt) for nr in manifest.nodes if nr.prompt]
    plan = manifest.production_plan
    env = dict(os.environ)
    models = _models_used(manifest, plan, env)
    bgm = _bgm_report(profile, plan, env)
    cost = estimate_cost(profile, plan, manifest, conformance, rubric)
    return FinalReport(
        run_id=run_id,
        user_input=echo,
        character=_character_summary(profile),
        style=_style_summary(profile),
        hook=_hook_summary(profile),
        storyboard=_storyboard_summary(profile),
        node_prompts=prompts,
        node_flow=[nr.name for nr in manifest.nodes],
        models_used=models,
        bgm_source=bgm,
        conformance=conformance,
        rubric=rubric,
        repair=repair or {},
        cost=cost,
    )


def _cost_section(cost: CostReport | None) -> list[str]:
    """예상 비용 섹션(모델별 표 + 합계 + caveats)을 마크다운 줄로 만든다."""
    if cost is None:
        return ["## 예상 비용", "-"]
    header = f"## 예상 비용 (단가 기준일 {cost.as_of}, {cost.currency}, 실제 청구와 다를 수 있음)"
    out = [header, ""]
    if cost.lines:
        out.append("| 항목 | 모델 | 단위 | 사용량 | 단가 | 소계 |")
        out.append("|---|---|---|---|---|---|")
        for ln in cost.lines:
            note = f" ({ln.note})" if ln.note else ""
            out.append(
                f"| {ln.label}{note} | {ln.model} | {ln.unit} | {ln.quantity:g} | "
                f"${ln.unit_price_usd:.3f} | ${ln.subtotal_usd:.3f} |"
            )
        out.append(f"| **합계** |  |  |  |  | **${cost.total_usd:.3f}** |")
    else:
        out.append("과금 대상 모델 사용 없음(로컬 폴백 경로). 예상 비용 $0.")
    out.append("")
    out += [f"- {c}" for c in cost.caveats]
    return out


def _kv_section(title: str, data: dict) -> list[str]:
    """dict를 '## 제목' + '- key: value' 목록으로. 비었으면 섹션을 만들지 않는다."""
    if not data:
        return []
    return [f"## {title}", *[f"- {k}: {v}" for k, v in data.items()], ""]


def _storyboard_section(rows: list) -> list[str]:
    """컷별 스토리보드를 타임코드 목록으로. 비었으면 생략."""
    if not rows:
        return []
    out = ["## 스토리보드"]
    for r in rows:
        beat = r.get("beat") or "-"
        sub = f' 자막:"{r["subtitle"]}"' if r.get("subtitle") else ""
        act = f" — {r['action']}" if r.get("action") else ""
        out.append(f"- `{r.get('t', '')}` [{beat}]{act}{sub}")
    out.append("")
    return out


def _bgm_section(bgm) -> str:
    """BGM을 'gen'만이 아니라 모델 + 음악 의도로 보인다."""
    parts = [f"방식 {bgm.kind}"]
    if bgm.model:
        parts.append(f"모델 {bgm.model}")
    if bgm.source:
        parts.append(f"출처 {bgm.source}")
    line = "## BGM\n- " + ", ".join(parts)
    if bgm.description:
        line += f"\n- 음악: {bgm.description}"
    return line


def render_report_md(report: FinalReport, out_path: str) -> str:
    e = report.user_input
    lines = [
        f"# 최종 리포트 — {report.run_id}",
        "",
        "## 유저 입력",
        f"- 목적: {e.objective}",
        f"- 제품: {e.product_input or '-'}",
        f"- 레퍼런스: {e.reference_ref or '-'}",
        "",
        *_kv_section("캐릭터", report.character),
        *_kv_section("스타일", report.style),
        *_kv_section("훅", report.hook),
        *_storyboard_section(report.storyboard),
        "## 최종 의견",
        report.final_opinion or "(미작성)",
        "",
        "## 노드 흐름",
        " -> ".join(report.node_flow) or "-",
        "",
        "## 사용 모델",
        ", ".join(f"{k}={v}" for k, v in report.models_used.items()) or "-",
        "",
        *_cost_section(report.cost),
        "",
        _bgm_section(report.bgm_source),
        "",
        f"## 평가\n- conformance: {report.conformance}\n- rubric: {report.rubric}",
        "",
        f"## verify 교정(repair)\n- 되돌린 횟수: {report.repair.get('attempts', 0)}\n"
        f"- 미해결 fail: {report.repair.get('unresolved') or '없음'}",
        "",
        "## 바이럴 예측",
        report.viral_prediction or "(미작성)",
        "",
        "## 노드별 프롬프트",
    ]
    lines += [f"### {p.node}\n{p.prompt}" for p in report.node_prompts] or ["-"]
    out = "\n".join(lines) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    return out_path
