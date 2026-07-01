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
from .analysis.profile import VideoProfile
from .analysis.reference import _find_project_root, download_via_script
from .analysis.reference import add_reference as add_reference_flow
from .analysis.rubric import evaluate_video
from .analysis.similarity import SimilarityReport, compare_profiles
from .generate.conformance import verify_conformance
from .generate.intake import intake, validate_purpose
from .generate.planning_graph import run_planning
from .generate.production_graph import run_production
from .generate.schema import GenerationInput, ReelProfile, RunManifest, Storyboard
from .generate.text_client import make_text_client

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
    ref = _load_profile(reference, use_gemini=not no_gemini)
    gen = _load_profile(output, use_gemini=not no_gemini)
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
    ok, reason = validate_purpose(brief, text_client=client)
    if not ok:
        typer.echo(f"거절: {reason}", err=True)
        raise typer.Exit(code=2)
    img = None if no_images else _make_image_client()
    path = run_planning(brief, outputs, text_client=client, image_client=img)
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
            manifest = run_production(brief, use_vlm=not no_vlm)
            typer.echo(f"영상: {manifest.final_video}", err=True)
            return

    text = None if no_llm else make_text_client()
    # 영상 목적이 제대로 서술되지 않았으면 실행 거절(그 외에는 목적만으로 나머지 추론).
    ok, reason = validate_purpose(brief, text_client=text)
    if not ok:
        typer.echo(f"거절: {reason}", err=True)
        raise typer.Exit(code=2)
    img = None if no_images else _make_image_client()

    # 레퍼런스가 있으면 한 번만 analyze해 비교 기준으로 재사용한다.
    ref_path = intake(brief).reference_ref
    ref_profile: VideoProfile | None = None
    if ref_path and not no_similarity and Path(ref_path).exists():
        typer.echo(f"레퍼런스 분석: {ref_path}", err=True)
        ref_profile = analyze_video(ref_path, use_gemini=text is not None)

    feedback = ""
    best: tuple[float, str] | None = None  # (overall, final_video)
    iters = max(1, max_iters) if ref_profile is not None else 1
    for i in range(iters):
        if i > 0:
            typer.echo(f"[반복 {i + 1}/{iters}] 유사도 미달 -> 피드백 재계획", err=True)
        path = run_planning(
            brief, outputs, text_client=text, image_client=img, style_feedback=feedback,
        )
        typer.echo(f"ReelProfile: {path}", err=True)
        manifest = run_production(str(path), use_vlm=not no_vlm)
        typer.echo(f"영상: {manifest.final_video}", err=True)

        if ref_profile is None or not manifest.final_video:
            return
        final_video = manifest.final_video
        gen_profile = analyze_video(final_video, use_gemini=text is not None)
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


def _print_plan_summary(profile_path: str) -> str | None:
    """확정 전 ReelProfile 요약을 보여준다. key_visual 절대경로를 돌려준다(있으면)."""
    from .generate.product import product_identity

    profile = ReelProfile.model_validate_json(Path(profile_path).read_text(encoding="utf-8"))
    plan_dir = Path(profile_path).parent
    kv = profile.asset_bible.key_visual
    kv_abs = str(plan_dir / kv) if kv else None
    lines = [
        "",
        "──────── 생성할 영상 요약 ────────",
        f"목적:   {profile.objective.goal[:90]}",
        f"제품:   {product_identity(profile.product)[:90]}",
        f"인물:   {(profile.character.look or '')[:80]}",
        f"음악:   {profile.music.style or '-'} / {profile.music.mood or '-'} / {profile.music.tempo or '-'}",
        f"컷수:   {len(profile.storyboard.panels)}컷, pacing={profile.style.pacing or '-'}",
        f"자막:   {[p.subtitle_text for p in profile.storyboard.panels if p.subtitle_text][:6]}",
        f"대표이미지(key_visual): {kv_abs or '없음'}",
        "─────────────────────────────────",
    ]
    typer.echo("\n".join(lines), err=True)
    return kv_abs


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

    from .generate.chat_intake import OPENING, ChatState, next_turn

    text = make_text_client()
    if text is None:
        typer.echo("chat 모드는 텍스트 LLM 키가 필요합니다(GEMINI_API_KEY 등).", err=True)
        raise typer.Exit(code=2)

    session: PromptSession = PromptSession()
    state = ChatState()
    typer.echo("리엘젠 챗 모드입니다. 만들고 싶은 숏폼 영상을 자유롭게 말씀해 주세요. (Ctrl-D로 종료)")

    def _ask(prompt_text: str) -> str:
        try:
            return session.prompt(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            typer.echo("\n종료합니다.", err=True)
            raise typer.Exit(code=0) from None

    if seed.strip():
        state.add_user(seed.strip())
    else:
        typer.echo(f"\n🤖 {OPENING}")
        state.add_user(_ask("나 > "))

    # 대화 루프: 충분해질 때까지 한 번에 하나씩 물어 브리프를 모은다(상한 가드).
    brief = ""
    for _ in range(8):
        decision = next_turn(state, text)
        if decision.ready and decision.brief:
            brief = decision.brief
            break
        question = decision.question or "조금 더 자세히 말씀해 주시겠어요?"
        state.add_assistant(question)
        typer.echo(f"\n🤖 {question}")
        state.add_user(_ask("나 > "))
    if not brief:
        brief = state.transcript()  # 상한 도달 시 대화 전체를 브리프로

    ok, reason = validate_purpose(brief, text_client=text)
    if not ok:
        typer.echo(f"\n거절: {reason}", err=True)
        raise typer.Exit(code=2)

    typer.echo("\n🤖 좋아요, 기획을 정리하고 대표 이미지를 만드는 중입니다...", err=True)
    img = None if no_images else _make_image_client()
    path = run_planning(brief, outputs, text_client=text, image_client=img)
    kv_abs = _print_plan_summary(str(path))
    if kv_abs and Path(kv_abs).exists():
        _open_file(kv_abs)  # 대표 이미지를 열어 미리 보여준다(맥)

    confirm = _ask("\n이대로 영상을 생성할까요? (y/n) > ").lower()
    if confirm not in ("y", "yes", "네", "응", "ㅇ", "예"):
        typer.echo(f"취소했습니다. ReelProfile은 저장돼 있습니다: {path}", err=True)
        raise typer.Exit(code=0)

    typer.echo("\n🤖 영상 생성 중입니다(수 분 소요)...", err=True)
    manifest = run_production(str(path), use_vlm=not no_vlm)
    out_dir = Path(manifest.final_video).parent if manifest.final_video else path.parent
    typer.echo(f"\n✅ 완료! 결과 폴더: {out_dir}", err=True)
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
