"""reel-gen-agent CLI.

현재 사용 가능한 명령:
- analyze: 레퍼런스 영상(로컬 파일) -> VideoProfile(JSON). 구현 완료.
- add-reference: URL 하나로 다운로드 -> 분석 -> 프로필 저장 -> 카탈로그. 구현 완료.
- evaluate: 영상 -> 드라이버 Rubric 채점(RubricResult JSON). 구현 완료.
- verify: 영상 -> Conformance 무결성·적합성 검증(ConformanceReport JSON). 구현 완료.
- plan: 입력 -> ReelProfile(JSON) 산출. 워킹 스켈레톤.
- execute: ReelProfile -> Production 실행 -> final.mp4 + upload.md + report.md. 워킹 스켈레톤.

설계만 된 명령(추후 구현):
- generate: 생성 입력 -> 에셋 바이블 -> 스토리보드 -> 영상. docs/pipeline-design.md 참고.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from .analysis.analyze import analyze_video
from .analysis.reference import _find_project_root, download_via_script
from .analysis.reference import add_reference as add_reference_flow
from .analysis.rubric import evaluate_video
from .generate.conformance import verify_conformance
from .generate.gates import GateConfig
from .generate.planning_graph import run_planning
from .generate.production_graph import run_production
from .generate.schema import GenerationInput, RunManifest, Storyboard

app = typer.Typer(
    add_completion=False,
    help="Analyze reference short-form videos and generate new vertical ad reels.",
)


def _read(path: str) -> str:
    """JSON 파일을 UTF-8 텍스트로 읽는다(verify의 입력 로딩용)."""
    return Path(path).read_text(encoding="utf-8")


def _is_url(value: str) -> bool:
    """http(s) URL이면 True. analyze가 URL과 로컬 경로를 구분하는 데 쓴다."""
    return value.startswith("http://") or value.startswith("https://")


@app.command()
def analyze(
    source: str = typer.Argument(..., help="분석할 영상: 로컬 파일 경로 또는 URL"),
    url: str | None = typer.Option(None, help="원본 URL(로컬 파일일 때 출처 기록용)"),
    out: str | None = typer.Option(None, help="JSON 저장 경로(미지정 시 stdout)"),
    cookies_from_browser: str | None = typer.Option(
        None,
        "--cookies-from-browser",
        help="URL 입력 시 로그인 필요 사이트용 브라우저 쿠키(예: chrome).",
    ),
    no_gemini: bool = typer.Option(
        False, "--no-gemini", help="비정형 계층(Gemini) 없이 정형 수치만"
    ),
) -> None:
    """레퍼런스 영상을 분석해 VideoProfile(JSON)을 출력한다.

    source는 로컬 파일 경로 또는 URL을 받는다. URL이면 먼저 내려받은 뒤 분석한다
    (카탈로그에는 추가하지 않는다. 카탈로그까지 원하면 add-reference를 쓴다).
    """
    video: str
    source_url: str | None
    if _is_url(source):
        try:
            root = _find_project_root()
            video_path = download_via_script(
                source, root, cookies_from_browser=cookies_from_browser
            )
        except Exception as exc:  # 다운로드 실패는 한 줄로
            typer.echo(f"다운로드 실패: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"내려받음: {video_path}", err=True)
        video, source_url = str(video_path), source
    else:
        if not Path(source).exists():
            typer.echo(f"파일 없음: {source}", err=True)
            raise typer.Exit(code=1)
        video, source_url = source, url

    profile = analyze_video(video, url=source_url, use_gemini=not no_gemini)
    payload = json.dumps(profile.model_dump(), ensure_ascii=False, indent=2)

    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"저장: {out}", err=True)
    else:
        typer.echo(payload)


@app.command(name="add-reference")
def add_reference(
    url: str = typer.Argument(..., help="레퍼런스 영상 URL(YouTube/TikTok/Instagram 등)"),
    cookies_from_browser: str | None = typer.Option(
        None,
        "--cookies-from-browser",
        help="로그인 필요 사이트용 브라우저 쿠키(예: chrome). Instagram 등에 필요.",
    ),
    no_gemini: bool = typer.Option(
        False, "--no-gemini", help="비정형 계층(Gemini) 없이 정형 수치만"
    ),
    no_catalog: bool = typer.Option(
        False, "--no-catalog", help="reference_video/list.md 항목 추가를 건너뛴다"
    ),
    no_evaluate: bool = typer.Option(
        False, "--no-evaluate", help="레퍼런스 Rubric 평가를 건너뛴다(기본은 함께 실행)"
    ),
) -> None:
    """URL 하나로 레퍼런스를 들인다: 다운로드 -> 분석 + 평가 -> 저장 -> 카탈로그.

    레퍼런스 분석은 analyze(프로필)와 evaluate(Rubric)를 기본으로 함께 돌린다.
    """
    try:
        result = add_reference_flow(
            url,
            cookies_from_browser=cookies_from_browser,
            use_gemini=not no_gemini,
            write_catalog=not no_catalog,
            evaluate=not no_evaluate,
        )
    except Exception as exc:  # 사용자에게는 한 줄 메시지로, 스택은 숨긴다.
        typer.echo(f"레퍼런스 추가 실패: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"영상:   {result.video_path}", err=True)
    typer.echo(f"프로필: {result.profile_path}", err=True)
    if result.rubric_path is not None and result.rubric is not None:
        verdict = "통과" if result.rubric.passed else "미달"
        typer.echo(
            f"평가:   {result.rubric_path} (gated={result.rubric.gated_score} -> {verdict})",
            err=True,
        )
    if result.catalog_path is not None:
        typer.echo(
            f"카탈로그: {result.catalog_path} (#{result.catalog_index} 항목 추가)",
            err=True,
        )


@app.command()
def evaluate(
    video: str = typer.Argument(..., help="채점할 영상 파일 경로"),
    out: str | None = typer.Option(None, help="JSON 저장 경로(미지정 시 stdout)"),
    no_gemini: bool = typer.Option(
        False, "--no-gemini", help="저지(Gemini)를 건너뛴다. 채점 불가로 보고."
    ),
) -> None:
    """영상을 드라이버 Rubric으로 채점해 RubricResult(JSON)을 출력한다.

    계약과 수식은 specs/rubric.md, 배경은 docs/rubric.md를 참고한다.
    """
    if not Path(video).exists():
        typer.echo(f"파일 없음: {video}", err=True)
        raise typer.Exit(code=1)

    result = evaluate_video(video, use_gemini=not no_gemini)
    payload = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)

    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"저장: {out}", err=True)
    else:
        typer.echo(payload)

    if result.scored:
        verdict = "통과" if result.passed else "미달"
        typer.echo(
            f"gated={result.gated_score} flat={result.flat_score} "
            f"게이트={'O' if result.gate_passed else 'X'} -> {verdict}",
            err=True,
        )


@app.command()
def verify(
    video: str = typer.Argument(..., help="검증할 영상 파일 경로"),
    input: str | None = typer.Option(None, "--input", help="generation_input.json(템플릿 적합성)"),
    storyboard: str | None = typer.Option(None, "--storyboard", help="storyboard.json(머지/교차)"),
    manifest: str | None = typer.Option(None, "--manifest", help="run.json(노드/머지 무결성)"),
    out: str | None = typer.Option(None, help="JSON 저장 경로(미지정 시 stdout)"),
    no_vlm: bool = typer.Option(False, "--no-vlm", help="VLM 지각 체크를 건너뛴다(결정론만)."),
) -> None:
    """영상이 의도대로 온전히 만들어졌는지 Conformance로 검증한다(하드 pass/fail).

    fail이 하나라도 있으면 exit code != 0. 계약은 specs/conformance-gate.md.
    """
    if not Path(video).exists():
        typer.echo(f"파일 없음: {video}", err=True)
        raise typer.Exit(code=1)

    gen_input = GenerationInput.model_validate_json(_read(input)) if input else None
    board = Storyboard.model_validate_json(_read(storyboard)) if storyboard else None
    run = RunManifest.model_validate_json(_read(manifest)) if manifest else None

    report = verify_conformance(
        video,
        gen_input=gen_input,
        storyboard=board,
        manifest=run,
        use_vlm=not no_vlm,
    )
    payload = json.dumps(report.model_dump(), ensure_ascii=False, indent=2)

    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"저장: {out}", err=True)
    else:
        typer.echo(payload)

    counts = report.counts
    verdict = "PASS" if report.passed else "FAIL"
    typer.echo(
        f"{verdict}  pass={counts.get('pass', 0)} fail={counts.get('fail', 0)} "
        f"skip={counts.get('skip', 0)}",
        err=True,
    )
    if not report.passed:
        fails = [c.code for c in report.checks if c.status == "fail"]
        typer.echo(f"실패 체크: {', '.join(fails)}", err=True)
        raise typer.Exit(code=1)


@app.command()
def plan(
    brief: str = typer.Argument(..., help="영상 목적/브리프 또는 입력"),
    outputs: str = typer.Option("outputs", help="출력 루트 디렉터리"),
    yes: bool = typer.Option(False, "-y", "--yes", help="모든 게이트 자동 승인"),
) -> None:
    """입력에서 ReelProfile을 만들어 outputs/<run_id>/에 저장한다."""
    cfg = GateConfig(mode="run" if yes else "ask")
    path = run_planning(brief, outputs, gate=cfg)
    typer.echo(f"ReelProfile: {path}", err=True)


@app.command()
def execute(
    profile: str = typer.Argument(..., help="ReelProfile JSON 경로"),
    no_vlm: bool = typer.Option(False, "--no-vlm", help="rubric 채점을 건너뛴다."),
) -> None:
    """ReelProfile을 받아 Production을 돌려 outputs/<run_id>/에 영상·리포트를 만든다."""
    if not Path(profile).exists():
        typer.echo(f"파일 없음: {profile}", err=True)
        raise typer.Exit(code=1)
    manifest = run_production(profile, use_vlm=not no_vlm)
    typer.echo(f"영상: {manifest.final_video}", err=True)


@app.command()
def generate(
    input_json: str = typer.Argument(..., help="generation_input.json 경로"),
) -> None:
    """[미구현] 생성 입력으로 영상을 만든다. 설계는 docs/pipeline-design.md 참고."""
    typer.echo(
        "generate 명령은 아직 구현되지 않았습니다. "
        "파이프라인 설계는 docs/pipeline-design.md를 참고하세요.",
        err=True,
    )
    raise typer.Exit(code=2)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
