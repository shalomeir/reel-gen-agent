"""reel-gen-agent CLI.

현재 사용 가능한 명령:
- analyze: 레퍼런스 영상 -> VideoProfile(JSON). 구현 완료.

설계만 된 명령(추후 구현):
- generate: 생성 입력 -> 에셋 바이블 -> 스토리보드 -> 영상. docs/pipeline-design.md 참고.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from .analysis.analyze import analyze_video

app = typer.Typer(
    add_completion=False,
    help="Analyze reference short-form videos and generate new vertical ad reels.",
)


@app.command()
def analyze(
    video: str = typer.Argument(..., help="분석할 영상 파일 경로"),
    url: Optional[str] = typer.Option(None, help="원본 URL(출처 기록용)"),
    out: Optional[str] = typer.Option(None, help="JSON 저장 경로(미지정 시 stdout)"),
    no_gemini: bool = typer.Option(
        False, "--no-gemini", help="비정형 계층(Gemini) 없이 정형 수치만"
    ),
) -> None:
    """레퍼런스 영상을 분석해 VideoProfile(JSON)을 출력한다."""
    if not Path(video).exists():
        typer.echo(f"파일 없음: {video}", err=True)
        raise typer.Exit(code=1)

    profile = analyze_video(video, url=url, use_gemini=not no_gemini)
    payload = json.dumps(profile.model_dump(), ensure_ascii=False, indent=2)

    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(payload + "\n", encoding="utf-8")
        typer.echo(f"저장: {out}", err=True)
    else:
        typer.echo(payload)


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
