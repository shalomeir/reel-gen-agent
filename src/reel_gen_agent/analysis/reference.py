"""URL 하나로 레퍼런스를 추가하는 오케스트레이터.

`utils/add-reference.sh`(다운로드)와 `analyze_video`(분석), `to_list_entry`(카탈로그)는
각각 한 가지 일만 한다. 이 모듈은 셋을 한 흐름으로 묶어 "URL을 넣으면 영상이 받아지고,
프로필 JSON이 생기고, reference_video/list.md에 항목이 추가된다"를 한 번에 보장한다.

분리 원칙은 유지한다. 다운로드 도구(yt-dlp 옵션)는 여전히 add-reference.sh 한 곳에만 있고,
분석은 analyze_video에만 있다. 이 모듈은 호출 순서와 산출물 저장만 책임진다.
테스트에서 네트워크 없이 돌도록 다운로더/분석기를 주입할 수 있게 했다.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .analyze import analyze_video
from .list_writer import to_list_entry
from .profile import VideoProfile

# list.md가 없을 때 처음 만들어 줄 머리말. 항목은 이 아래로 계속 쌓인다.
_CATALOG_HEADER = """# 레퍼런스 영상 목록

이 폴더에 모은 영상들의 출처와 "왜 넣었는가"를 적어둔다. 영상 파일만 봐서는
의도를 알 수 없으니, 추가할 때마다 아래에 한 항목씩 늘린다.

`utils/add-reference.sh`로 받은 뒤 `reel-gen add-reference <url>`이 이 항목을 자동으로
추가한다. "넣은 의도"는 사람이 채우는 자리다.

---

## 목록

"""

# list.md 안의 "### 3. 제목" 같은 항목 머리를 찾아 다음 인덱스를 계산한다.
_ENTRY_HEADING = re.compile(r"^###\s+(\d+)\.", re.MULTILINE)

# yt-dlp 파일명 규칙 "제목 [Source-id]"에서 제목만 떼어내기 위한 패턴.
_SOURCE_SUFFIX = re.compile(r"\s*\[[^\]]+\]$")


@dataclass
class AddReferenceResult:
    """add_reference의 산출물 묶음."""

    video_path: Path
    profile: VideoProfile
    profile_path: Path
    catalog_path: Path | None
    catalog_index: int | None


def download_via_script(
    url: str,
    project_root: Path,
    cookies_from_browser: str | None = None,
) -> Path:
    """utils/add-reference.sh를 호출해 영상을 받고 저장 경로를 돌려준다.

    다운로드 옵션을 Python으로 복제하지 않고 스크립트에 위임해, yt-dlp 옵션이
    프로젝트에서 한 곳에만 존재하도록 유지한다.
    """
    script = project_root / "utils" / "add-reference.sh"
    if not script.exists():
        raise FileNotFoundError(f"다운로드 스크립트를 찾을 수 없음: {script}")

    cmd = ["bash", str(script), url]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]

    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # 스크립트는 저장 경로를 STDOUT 마지막 줄에 찍는다(경고는 STDERR).
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    if not lines:
        raise RuntimeError("다운로드는 끝났지만 저장 경로를 받지 못함")
    return Path(lines[-1].strip())


def _title_from_path(video_path: Path) -> str:
    """파일명에서 출처 꼬리표([Source-id])를 떼고 제목만 남긴다."""
    return _SOURCE_SUFFIX.sub("", video_path.stem).strip() or video_path.stem


def _next_catalog_index(catalog_path: Path) -> int:
    """list.md의 마지막 항목 번호 + 1. 비어 있으면 1."""
    if not catalog_path.exists():
        return 1
    indices = [int(m) for m in _ENTRY_HEADING.findall(catalog_path.read_text("utf-8"))]
    return max(indices) + 1 if indices else 1


def _append_catalog_entry(catalog_path: Path, entry_md: str) -> None:
    """list.md에 항목을 덧붙인다. 파일이 없으면 머리말부터 만든다."""
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    if not catalog_path.exists():
        catalog_path.write_text(_CATALOG_HEADER, encoding="utf-8")
    existing = catalog_path.read_text("utf-8")
    sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    catalog_path.write_text(existing + sep + entry_md, encoding="utf-8")


def add_reference(
    url: str,
    *,
    project_root: Path | None = None,
    cookies_from_browser: str | None = None,
    use_gemini: bool = True,
    write_catalog: bool = True,
    downloader: Callable[..., Path] = download_via_script,
    analyzer: Callable[..., VideoProfile] = analyze_video,
) -> AddReferenceResult:
    """URL 하나로 레퍼런스를 추가한다: 다운로드 -> 분석 -> 프로필 저장 -> 카탈로그.

    Args:
        url: 받을 영상 URL.
        project_root: 레포 루트. 미지정 시 이 파일 기준으로 자동 탐색.
        cookies_from_browser: 로그인 필요 사이트용 브라우저 이름(예: "chrome").
        use_gemini: 비정형 계층(Gemini) 사용 여부.
        write_catalog: reference_video/list.md 항목 추가 여부.
        downloader, analyzer: 테스트용 주입 지점.

    Returns:
        AddReferenceResult: 영상/프로필 경로와 카탈로그 인덱스.
    """
    root = project_root or _find_project_root()
    video_path = downloader(
        url, root, cookies_from_browser=cookies_from_browser
    )
    if not video_path.exists():
        raise FileNotFoundError(f"다운로드한 파일을 찾을 수 없음: {video_path}")

    profile = analyzer(str(video_path), url=url, use_gemini=use_gemini)

    # 프로필은 재생성 가능한 산출물이라 gitignore된 profiles/ 아래에 둔다.
    profiles_dir = root / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    profile_path = profiles_dir / f"{video_path.stem}.json"
    payload = json.dumps(profile.model_dump(), ensure_ascii=False, indent=2)
    profile_path.write_text(payload + "\n", encoding="utf-8")

    catalog_path: Path | None = None
    catalog_index: int | None = None
    if write_catalog:
        catalog_path = root / "reference_video" / "list.md"
        catalog_index = _next_catalog_index(catalog_path)
        entry = to_list_entry(profile, _title_from_path(video_path), catalog_index)
        _append_catalog_entry(catalog_path, entry)

    return AddReferenceResult(
        video_path=video_path,
        profile=profile,
        profile_path=profile_path,
        catalog_path=catalog_path,
        catalog_index=catalog_index,
    )


def _find_project_root() -> Path:
    """이 파일에서 위로 올라가며 pyproject.toml이 있는 디렉터리를 레포 루트로 본다."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parents[-1]
