"""report 노드: 회차 종합 리포트(FinalReport -> report.md).

레이아웃: 유저 입력(앞단) -> 의견 -> 노드 흐름 -> 모델 -> bgm -> eval -> 예측 ->
노드별 프롬프트(뒤). 렌더링은 결정론, final_opinion/viral_prediction만 LLM(여기선 빈값).
"""

from __future__ import annotations

from .cost import estimate_cost
from .schema import (
    BgmReport,
    CostReport,
    FinalReport,
    NodePrompt,
    ReelProfile,
    RunManifest,
    UserInputEcho,
)


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
    models = {"video": plan.video_model} if plan else {}
    bgm = BgmReport(kind=(plan.bgm if plan else "none"))
    cost = estimate_cost(profile, plan, manifest, conformance, rubric)
    return FinalReport(
        run_id=run_id,
        user_input=echo,
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
        f"## BGM\n- {report.bgm_source.kind}",
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
