"""run_id 명명과 출력 폴더. run_id = <concept-slug>-<YYYYMMDD-HHMMSS>.

plan이 이 폴더를 만들고 ReelProfile을 쓴다. execute는 같은 폴더를 채운다
(specs/information-schema.md "출력 폴더 구조").
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path


def slugify(concept: str, max_words: int = 5) -> str:
    norm = unicodedata.normalize("NFKD", concept).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-zA-Z0-9]+", norm.lower())
    return "-".join(words[:max_words]) or "reel"


def make_run_id(concept: str, now: datetime | None = None) -> str:
    ts = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"{slugify(concept)}-{ts}"


def create_run_dir(outputs_root: str, run_id: str) -> Path:
    d = Path(outputs_root) / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def profile_filename(run_id: str) -> str:
    return f"ReelProfile-{run_id}.json"
