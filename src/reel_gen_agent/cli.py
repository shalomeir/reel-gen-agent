"""reel-gen-agent CLI.

현재 사용 가능한 명령:
- analyze: 레퍼런스 영상(로컬 파일) -> VideoProfile(JSON). 구현 완료.
- add-reference: URL 하나로 다운로드 -> 분석 -> 프로필 저장 -> 카탈로그. 구현 완료.
- evaluate: 영상 -> 드라이버 Rubric 채점(RubricResult JSON). 구현 완료.
- verify: 영상 -> Conformance 무결성·적합성 검증(ConformanceReport JSON). 구현 완료.
- plan: 입력 -> ReelProfile(JSON) 산출. 워킹 스켈레톤.
- execute: ReelProfile -> Production 실행 -> final.mp4 + upload.md + report.md. 워킹 스켈레톤.
- rerun: 기존 ReelProfile로 정체성은 고정하고 style→훅→스토리→나레이션→음악을 재생성(새 폴더) -> Production.
- run: 입력 -> ReelProfile -> Production을 확인 게이트 없이 한 번에. 유사도 루프 포함.
- chat: plan/execute를 엮은 대화형 진입점.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import typer

from .analysis.analyze import analyze_video
from .analysis.profile import VideoProfile
from .analysis.reference import _find_project_root, download_via_script
from .analysis.reference import add_reference as add_reference_flow
from .analysis.rubric import evaluate_video
from .analysis.similarity import SimilarityReport, compare_profiles
from .generate.backends.veo import VeoImageRAIError
from .generate.conformance import verify_conformance
from .generate.intake import intake, normalized_input_to_brief, validate_purpose
from .generate.planning_graph import run_planning, run_replan
from .generate.product import ProductGroundingError
from .generate.production_graph import run_production
from .generate.schema import GenerationInput, ReelProfile, RunManifest, Storyboard
from .generate.text_client import make_text_client


def _quiet_genai_logs() -> None:
    """google-genai가 매 호출마다 찍는 정보/경고 로그를 억제한다(예: 'Both GOOGLE_API_KEY...').

    두 키를 다 설정해도 동작에는 문제가 없어(GOOGLE_API_KEY 우선) 반복 경고만 시끄럽다. CLI
    출력(대화·스피너)을 깨끗하게 유지하려고 이 로거만 ERROR로 올린다.
    """
    logging.getLogger("google_genai").setLevel(logging.ERROR)


_STATUS_CONSOLE = None


def _working(msg: str, fn):
    """비대화 명령의 대기 표시. stderr에 로딩 스피너(...)를 띄우고 fn을 돌려 결과를 반환한다.

    stdout(analyze/evaluate/verify가 찍는 JSON payload)은 건드리지 않는다. TTY가 아니면(파이프/CI)
    스피너 제어문자 대신 한 줄만 찍고 조용히 실행한다.
    """
    global _STATUS_CONSOLE
    from rich.console import Console

    if _STATUS_CONSOLE is None:
        _STATUS_CONSOLE = Console(stderr=True)
    if not _STATUS_CONSOLE.is_terminal:
        _STATUS_CONSOLE.print(f"… {msg}")
        return fn()
    with _STATUS_CONSOLE.status(f"[cyan]{msg}[/]", spinner="simpleDots"):
        return fn()


app = typer.Typer(
    add_completion=False,
    help="Analyze reference short-form videos and generate new vertical ad reels.",
)


def _read(path: str) -> str:
    """JSON 파일을 UTF-8 텍스트로 읽는다(verify의 입력 로딩용)."""
    return Path(path).read_text(encoding="utf-8")


def _planning_brief(source: str, *, text_client=None) -> str:
    """입력 파일이면 내용 기반으로, 아니면 원문 기반으로 plan 그래프용 브리프를 만든다."""
    source_path = Path(source)
    if source_path.exists() and source_path.is_file():
        return normalized_input_to_brief(
            _read(source), text_client=text_client, base_dir=source_path.parent
        )
    return source


def _produce(profile_path: str, *, use_vlm: bool):
    """Production을 돌리되 인물 이미지-RAI 차단은 트레이스백 대신 거절로 끝낸다.

    생성 인물이 실존·식별 가능한 인물과 유사해 영상 모델(Veo) 안전 필터에 막히면, 스틸로
    덮어 가짜 초상 광고를 만들지 않고 사유를 리턴하며 종료한다(exit code 2).
    """
    try:
        return run_production(profile_path, use_vlm=use_vlm)
    except VeoImageRAIError as exc:
        typer.echo(f"거절(RAI): {exc}", err=True)
        typer.echo(
            "→ 실존 인물을 특정하지 않는 인물로 바꾸거나, 캐릭터 참조 이미지 없이 다시 시도하세요.",
            err=True,
        )
        raise typer.Exit(code=2) from exc


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

    profile = _working("레퍼런스 분석 중", lambda: analyze_video(video, url=source_url, use_gemini=not no_gemini))
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

    result = _working("Rubric 채점 중", lambda: evaluate_video(video, use_gemini=not no_gemini))
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

    report = _working(
        "Conformance 검증 중",
        lambda: verify_conformance(
            video, gen_input=gen_input, storyboard=board, manifest=run, use_vlm=not no_vlm
        ),
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


def _load_profile(source: str, *, use_gemini: bool) -> VideoProfile:
    """VideoProfile을 얻는다: JSON이면 그대로 로드, 영상이면 analyze로 산출."""
    if source.endswith(".json"):
        return VideoProfile.model_validate_json(_read(source))
    return analyze_video(source, use_gemini=use_gemini)


def _print_similarity(report: SimilarityReport) -> None:
    """유사도 리포트를 사람이 읽게 stderr로 요약 출력한다."""
    verdict = "유사" if report.passed else "상이"
    typer.echo(
        f"유사도 overall={report.overall} (임계 {report.threshold}) -> {verdict}", err=True
    )
    for ax in report.axes:
        mark = "O" if ax.score >= 0.6 else "X"
        typer.echo(f"  [{mark}] {ax.key:9s} {ax.score:.2f}  {ax.detail}", err=True)


@app.command()
def compare(
    reference: str = typer.Option(..., "--reference", help="레퍼런스: VideoProfile JSON 또는 영상"),
    output: str = typer.Option(..., "--output", help="생성물: VideoProfile JSON 또는 영상"),
    out: str | None = typer.Option(None, help="SimilarityReport JSON 저장 경로(미지정 시 stdout)"),
    no_gemini: bool = typer.Option(
        False, "--no-gemini", help="영상 입력을 분석할 때 Gemini 지각 계층을 끈다"
    ),
) -> None:
    """생성물이 레퍼런스와 같은 결인지 유사도를 잰다(SimilarityReport JSON, 미달 시 exit!=0).

    두 입력은 각각 VideoProfile JSON이거나 영상 파일이다. 영상이면 analyze로 프로필을 만든다.
    계약은 specs/similarity-loop.md.
    """
    ref = _working("레퍼런스 분석 중", lambda: _load_profile(reference, use_gemini=not no_gemini))
    gen = _working("생성물 분석 중", lambda: _load_profile(output, use_gemini=not no_gemini))
    report = compare_profiles(ref, gen)
    payload = json.dumps(report.model_dump(), ensure_ascii=False, indent=2)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"저장: {out}", err=True)
    else:
        typer.echo(payload)
    _print_similarity(report)
    if not report.passed:
        raise typer.Exit(code=1)


@app.command()
def plan(
    brief: str = typer.Argument(..., help="영상 목적/브리프 또는 입력"),
    outputs: str = typer.Option("outputs", help="출력 루트 디렉터리"),
    no_llm: bool = typer.Option(False, "--no-llm", help="LLM 없이(후크 생략) 결정론 콘티만"),
    no_images: bool = typer.Option(False, "--no-images", help="이미지 생성 없이(폴백만)"),
) -> None:
    """입력에서 ReelProfile을 만들어 outputs/<run_id>/에 저장한다(확인 게이트 없이 한 번에).

    영상 목적이 명확하지 않으면 거절한다. 그 외에는 목적만으로 나머지를 추론해 채운다.
    """
    client = None if no_llm else make_text_client()
    planning_brief = _planning_brief(brief, text_client=client)
    ok, reason = validate_purpose(planning_brief, text_client=client)
    if not ok:
        typer.echo(f"거절: {reason}", err=True)
        raise typer.Exit(code=2)
    img = None if no_images else _make_image_client()
    path = _working(
        "기획 중 (ReelProfile·에셋 생성)",
        lambda: run_planning(planning_brief, outputs, text_client=client, image_client=img),
    )
    typer.echo(f"ReelProfile: {path}", err=True)


@app.command()
def execute(
    profile: str = typer.Argument(..., help="ReelProfile JSON 경로"),
    no_vlm: bool = typer.Option(False, "--no-vlm", help="rubric 채점을 건너뛴다."),
) -> None:
    """ReelProfile을 받아 Production을 돌려 outputs/<run_id>/에 영상·리포트를 만든다.

    프로필을 있는 그대로 렌더한다. 같은 정체성으로 다른 어프로치 1편을 뽑고 싶으면 rerun을 쓴다.
    """
    if not Path(profile).exists():
        typer.echo(f"파일 없음: {profile}", err=True)
        raise typer.Exit(code=1)
    manifest = _working("영상 생성 중 (production)", lambda: _produce(profile, use_vlm=not no_vlm))
    typer.echo(f"영상: {manifest.final_video}", err=True)


@app.command()
def rerun(
    profile: str = typer.Argument(..., help="기존 ReelProfile JSON 경로"),
    outputs: str = typer.Option("outputs", help="출력 루트 디렉터리(재생성물의 새 폴더 위치)"),
    no_vlm: bool = typer.Option(False, "--no-vlm", help="rubric 채점을 건너뛴다."),
) -> None:
    """기존 ReelProfile로 다른 어프로치 1편을 다시 뽑는다: 정체성 고정, narrative 재생성 -> production.

    정체성(제품·모델·에셋)은 그대로 두고 style→훅→스토리→나레이션→음악을 새로 전개한 새
    ReelProfile(새 폴더)을 만든 뒤, 그걸로 production을 돌린다("같은 시스템, 다른 결과" 증명).
    replan은 레퍼런스를 무시하고 style부터 재생성하므로 매번 다른 결과가 나온다.
    """
    if not Path(profile).exists():
        typer.echo(f"파일 없음: {profile}", err=True)
        raise typer.Exit(code=1)
    text = make_text_client()
    if text is None:
        typer.echo("rerun은 텍스트 LLM 키가 필요합니다(GEMINI_API_KEY 등).", err=True)
        raise typer.Exit(code=2)
    img = _make_image_client()  # key_visual 재생성용(없으면 원본 커버 폴백)
    new_path = _working(
        "재기획 중 (새 style→훅→스토리→나레이션→음악)",
        lambda: run_replan(profile, outputs, text_client=text, image_client=img),
    )
    typer.echo(f"재기획: 새 폴더 {new_path}", err=True)
    manifest = _working(
        "영상 생성 중 (production)", lambda: _produce(str(new_path), use_vlm=not no_vlm)
    )
    typer.echo(f"영상: {manifest.final_video}", err=True)


def _make_image_client():
    """가용하면 실제 Nano Banana 이미지 클라이언트를, 자격이 없으면 None을 돌려준다."""
    from .analysis.gemini_client import select_backend
    from .generate.image_client import NanoBananaImageClient

    return NanoBananaImageClient() if select_backend() is not None else None


@app.command()
def run(
    brief: str = typer.Argument(..., help="영상 목적/브리프 또는 입력"),
    outputs: str = typer.Option("outputs", help="출력 루트 디렉터리"),
    no_vlm: bool = typer.Option(False, "--no-vlm", help="rubric 채점을 건너뛴다."),
    no_llm: bool = typer.Option(False, "--no-llm", help="텍스트 LLM 없이 결정론 콘티만"),
    no_images: bool = typer.Option(False, "--no-images", help="이미지 생성 없이(폴백만)"),
    max_iters: int = typer.Option(
        1, "--max-iters", help="레퍼런스가 있을 때 유사도 미달이면 재계획·재생성할 최대 횟수"
    ),
    no_similarity: bool = typer.Option(
        False, "--no-similarity", help="레퍼런스가 있어도 유사도 비교/루프를 건너뛴다"
    ),
) -> None:
    """입력 -> ReelProfile -> production을 한 번에 밀어붙인다(확인 게이트 없음).

    입력이 ReelProfile JSON이면 계획을 건너뛰고 바로 production을 실행한다. 그 외에는 입력에
    영상 목적이 명확히 서술됐는지 먼저 확인하고(없으면 거절), 목적만으로 나머지를 추론해
    ReelProfile을 만든 뒤 production으로 간다. 레퍼런스가 있고 max_iters>1이면, 생성물을 다시
    analyze해 레퍼런스와 유사도를 비교하고, 미달이면 축별 델타를 plan 피드백으로 밀어 넣어
    재계획·재생성한다(유사해질 때까지, 최대 max_iters회, specs/similarity-loop.md).
    """
    # ReelProfile이 주어지면 계획을 건너뛰고 바로 production.
    if brief.endswith(".json") and Path(brief).exists():
        try:
            ReelProfile.model_validate_json(Path(brief).read_text(encoding="utf-8"))
        except Exception:
            pass  # ReelProfile이 아니면 일반 브리프로 진행
        else:
            typer.echo("ReelProfile 감지 -> 바로 production 실행", err=True)
            manifest = _working("영상 생성 중 (production)", lambda: _produce(brief, use_vlm=not no_vlm))
            typer.echo(f"영상: {manifest.final_video}", err=True)
            return

    text = None if no_llm else make_text_client()
    planning_brief = _planning_brief(brief, text_client=text)
    # 영상 목적이 제대로 서술되지 않았으면 실행 거절(그 외에는 목적만으로 나머지 추론).
    ok, reason = validate_purpose(planning_brief, text_client=text)
    if not ok:
        typer.echo(f"거절: {reason}", err=True)
        raise typer.Exit(code=2)
    img = None if no_images else _make_image_client()

    # 레퍼런스가 있으면 한 번만 analyze해 비교 기준으로 재사용한다.
    ref_path = intake(planning_brief).reference_ref
    if ref_path and _is_url(ref_path):
        try:
            root = _find_project_root()
            video_path = download_via_script(ref_path, root)
        except Exception as exc:
            typer.echo(f"레퍼런스 다운로드 실패: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f"레퍼런스 내려받음: {video_path}", err=True)
        planning_brief = planning_brief.replace(ref_path, str(video_path), 1)
        ref_path = str(video_path)
    ref_profile: VideoProfile | None = None
    if ref_path and not no_similarity and Path(ref_path).exists():
        typer.echo(f"레퍼런스 분석: {ref_path}", err=True)
        ref_profile = _working("레퍼런스 분석 중", lambda: analyze_video(ref_path, use_gemini=text is not None))

    feedback = ""
    best: tuple[float, str] | None = None  # (overall, final_video)
    iters = max(1, max_iters) if ref_profile is not None else 1
    for i in range(iters):
        if i > 0:
            typer.echo(f"[반복 {i + 1}/{iters}] 유사도 미달 -> 피드백 재계획", err=True)
        path = _working(
            "기획 중 (ReelProfile·에셋 생성)",
            lambda f=feedback: run_planning(
                planning_brief, outputs, text_client=text, image_client=img, style_feedback=f
            ),
        )
        typer.echo(f"ReelProfile: {path}", err=True)
        manifest = _working("영상 생성 중 (production)", lambda p=path: _produce(str(p), use_vlm=not no_vlm))
        typer.echo(f"영상: {manifest.final_video}", err=True)

        if ref_profile is None or not manifest.final_video:
            return
        final_video = manifest.final_video
        gen_profile = _working("생성물 분석 중", lambda fv=final_video: analyze_video(fv, use_gemini=text is not None))
        report = compare_profiles(ref_profile, gen_profile)
        # 유사도 리포트를 생성물 폴더에 남겨 증거로 보존한다(레퍼런스 대비 결 일치도).
        sim_path = Path(final_video).parent / "similarity.json"
        sim_path.write_text(
            json.dumps(report.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _print_similarity(report)
        if best is None or report.overall > best[0]:
            best = (report.overall, final_video)
        if report.passed:
            typer.echo(f"레퍼런스와 유사 달성(overall={report.overall}).", err=True)
            return
        feedback = report.feedback()  # 다음 반복에 밀어 넣을 축별 델타

    if best is not None:
        typer.echo(
            f"최대 반복 종료. 최고 유사도 overall={best[0]} -> {best[1]}", err=True
        )


def _open_file(path: str) -> None:
    """로컬(맥)에서 파일을 기본 앱으로 연다(best-effort). 실패해도 조용히 넘어간다."""
    import subprocess
    import sys as _sys

    try:
        if _sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
    except Exception:
        pass


def _print_plan_summary(profile_path: str) -> tuple[str | None, Path]:
    """확정 전 ReelProfile 요약 + 생성물 폴더·에셋 경로를 보여준다.

    사용자가 폴더를 직접 열어 캐릭터·제품·대표이미지·ReelProfile을 보고 의견을 낼 수 있게
    각 파일의 정확한 경로를 표기한다. (key_visual 절대경로, plan 폴더)를 돌려준다.
    """
    from .generate.product import product_identity

    profile = ReelProfile.model_validate_json(Path(profile_path).read_text(encoding="utf-8"))
    plan_dir = Path(profile_path).parent.resolve()

    def _asset(rel: str | None) -> str:
        return str(plan_dir / rel) if rel else "없음"

    kv = profile.asset_bible.key_visual
    kv_abs = str(plan_dir / kv) if kv else None
    pkg = next((v.image for v in profile.asset_bible.product.views if v.image), None)
    lines = [
        "",
        "──────── 생성할 영상 요약 ────────",
        f"목적:   {profile.objective.goal[:90]}",
        f"제품:   {product_identity(profile.product)[:90]}",
        f"인물:   {(profile.character.look or '')[:80]}",
        f"음악:   {profile.music.style or '-'} / {profile.music.mood or '-'} / {profile.music.tempo or '-'}",
        f"컷수:   {len(profile.storyboard.panels)}컷, pacing={profile.style.pacing or '-'}",
        f"자막:   {[p.subtitle_text for p in profile.storyboard.panels if p.subtitle_text][:6]}",
        "",
        "── 생성물 폴더(직접 열어 확인) ──",
        f"기획 폴더:      {plan_dir}",
        f"ReelProfile:   {Path(profile_path).resolve()}",
        f"캐릭터 비주얼:  {_asset(profile.asset_bible.character.key_shot_image)}",
        f"제품 히어로:    {_asset(profile.asset_bible.product.hero_image)}",
        f"제품 패키지:    {_asset(pkg)}",
        f"대표이미지(key_visual): {kv_abs or '없음'}",
        "─────────────────────────────────",
    ]
    typer.echo("\n".join(lines), err=True)
    return kv_abs, plan_dir


@app.command()
def chat(
    seed: str = typer.Argument("", help="선택: 시작 브리프(비우면 대화로 시작)"),
    outputs: str = typer.Option("outputs", help="출력 루트 디렉터리"),
    no_vlm: bool = typer.Option(False, "--no-vlm", help="rubric 채점을 건너뛴다."),
    no_images: bool = typer.Option(False, "--no-images", help="이미지 생성 없이(폴백만)"),
) -> None:
    """대화형 챗 모드. 필요한 걸 물어 채우고, ReelProfile+대표이미지를 만든 뒤 확인받고 생성한다.

    입력 없이 시작하면 "어떤 숏폼 영상을 만들까요?"로 열어 목적·제품·레퍼런스·바이브를 자연스럽게
    물어본다. 충분해지면 ReelProfile과 key_visual을 만들어 요약을 보여주고, confirm하면 production을
    돌려 결과 폴더를 안내한다. 텍스트 LLM 키가 필요하다.
    """
    from prompt_toolkit import PromptSession
    from rich.console import Console

    from .generate.chat_intake import OPENING, ChatState, next_turn

    _quiet_genai_logs()
    text = make_text_client()
    if text is None:
        typer.echo("chat 모드는 텍스트 LLM 키가 필요합니다(GEMINI_API_KEY 등).", err=True)
        raise typer.Exit(code=2)

    console = Console()
    # 실행 시 기본 모델을 최상단에 보여준다(대화 모델 / 영상 생성 모델).
    text_model = getattr(text, "model", "?")
    video_model = os.environ.get("VEO_MODEL") or "veo-3.1-fast-generate-001"
    console.print("릴젠 챗 모드입니다. 만들고 싶은 숏폼 영상을 자유롭게 말씀해 주세요. (Ctrl-D로 종료)")
    console.print(f"[dim]대화 모델:[/] {text_model}")
    console.print(f"[dim]영상 생성 모델:[/] {video_model}")

    session: PromptSession = PromptSession()
    state = ChatState()

    def _ask(prompt_text: str) -> str:
        try:
            return session.prompt(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n종료합니다.")
            raise typer.Exit(code=0) from None

    def _spin(msg: str, fn):
        """처리 중 상태(뭐 하는지) + 로딩(...) 스피너를 띄우고 fn을 돌린다."""
        with console.status(f"[cyan]{msg}[/]", spinner="simpleDots"):
            return fn()

    if seed.strip():
        state.add_user(seed.strip())
    else:
        console.print(f"\n🤖 {OPENING}")
        state.add_user(_ask("나 > "))

    # 대화 루프: 목적·제품·캐릭터(등장 인물)가 정해질 때까지 한 번에 하나씩 물어 채운다.
    # 캐릭터는 사용자에게 반드시 한 번 되묻는다(사용자가 위임하면 그대로 수용). 덜 정의되면
    # next_turn이 계속 질문을 돌려주고, 충분해지면 ready=True로 브리프를 종합한다.
    brief = ""
    for _ in range(14):
        decision = _spin("생각하는 중", lambda: next_turn(state, text))
        if decision.ready and decision.brief:
            brief = decision.brief
            break
        question = decision.question or "조금 더 자세히 말씀해 주시겠어요?"
        state.add_assistant(question)
        console.print(f"\n🤖 {question}")
        state.add_user(_ask("나 > "))
    if not brief:
        brief = state.transcript()  # 상한 도달 시 대화 전체를 브리프로

    ok, reason = validate_purpose(brief, text_client=text)
    if not ok:
        console.print(f"\n거절: {reason}")
        raise typer.Exit(code=2)

    img = None if no_images else _make_image_client()
    # 수정 루프: 계획(ReelProfile+스토리보드+대표이미지)을 보여주고, 마음에 안 들면 피드백을
    # 받아 반영해 다시 만든다. y(확인)여야 생성으로 넘어간다(chat의 핵심: 계속 다듬기).
    feedback = ""
    path: Path | None = None
    while True:
        try:
            path = _spin(
                "기획을 정리하고 대표 이미지를 만드는 중",
                lambda b=brief, f=feedback: run_planning(
                    b, outputs, text_client=text, image_client=img, style_feedback=f
                ),
            )
        except ProductGroundingError as e:
            # 제품을 실제 소스로 확보하지 못한 경우. 임의 추정 대신 사용자에게 다시 묻고 재시도한다.
            console.print(f"\n🤖 {e}")
            resp = _ask("제품 URL(권장)이나 제품 이미지 경로, 또는 구체적인 제품 설명을 알려주세요 > ")
            if not resp:
                console.print("종료합니다.")
                raise typer.Exit(code=2) from None
            brief = f"{brief}\n제품: {resp}"
            continue
        except ValueError as e:
            # 그 외 계획 불가 사유. 가짜로 진행하지 않고 사유를 알린 뒤 종료한다.
            console.print(f"\n[red]계획을 세우지 못했습니다:[/] {e}")
            raise typer.Exit(code=2) from None
        kv_abs, plan_dir = _print_plan_summary(str(path))
        _open_file(str(plan_dir))  # 기획 폴더를 열어 캐릭터·제품·대표이미지를 직접 보게 한다(맥)
        if kv_abs and Path(kv_abs).exists():
            _open_file(kv_abs)  # 대표 이미지도 바로 미리 보여준다
        resp = _ask("\n이대로 생성할까요? (y=생성 / 수정할 점을 말하면 반영해 다시 보여드립니다) > ")
        if resp.lower() in ("y", "yes", "네", "응", "ㅇ", "예"):
            break
        if not resp:
            continue
        # 수정 요청을 브리프·피드백에 반영해 재계획한다(목적·제품·캐릭터·음악·스토리보드 등 폭넓게).
        brief = f"{brief}\n[수정 요청] {resp}"
        feedback = resp
        console.print("\n🤖 반영해 다시 정리할게요.")

    console.print("\n🤖 영상 생성 중입니다(수 분 소요)...")
    manifest = _spin("영상을 생성하는 중", lambda: _produce(str(path), use_vlm=not no_vlm))
    out_dir = Path(manifest.final_video).parent if manifest.final_video else path.parent
    console.print(f"\n✅ 완료! 결과 폴더: {out_dir}")
    console.print(f"영상: {manifest.final_video}")


def main() -> None:
    _quiet_genai_logs()
    app()


if __name__ == "__main__":
    main()
