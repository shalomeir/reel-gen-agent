# Plan Stage (Planning) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `plan` stage that turns an input (objective + optional character/product + optional reference) into a frozen `ReelProfile-<concept>-<datetime>.json` under `outputs/<run_id>/`, running intake, concept, hook, product analysis, asset bible, environment, storyboard, scripting, and profile assembly behind human-in-the-loop gates.

**Architecture:** A LangGraph planning graph whose nodes communicate through the pydantic schemas in `generate/schema.py`. LLM and image calls sit behind small injected client interfaces so tests mock them and the deterministic glue (gates, seeding, assembly, file naming) is covered by real assertions. The walking skeleton produces a valid ReelProfile from a minimal input with all model calls stubbed.

**Tech Stack:** Python 3.10+, pydantic v2, LangGraph, typer + rich. Tests with pytest; external model calls mocked.

## Global Constraints

- Python 3.10+, four-space indent, PEP 8. `snake_case` functions/vars, `PascalCase` classes, `UPPER_SNAKE_CASE` constants. Modules `snake_case`, docs/scripts `kebab-case`. UTF-8, trailing newline.
- Run everything inside the worktree-local `.venv` (`uv sync --extra dev` first). Never the global/pyenv Python. Use `uv run <cmd>`.
- Schemas are the only boundary. plan produces `ReelProfile`; it must compose existing schema types from `generate/schema.py`, never invent parallel ones. ([ADR.md](../../../specs/ADR.md) ADR-0003)
- Model-agnostic: text/image model IDs and `TEXT_MODEL_PRIORITY`/`GENAI_BACKEND` come from `.env`. The planning text LLM is a variable (Gemini 3.1 Pro vs Claude Opus). ([ADR.md] ADR-0008, [ai-model-records.md](../../../specs/ai-model-records.md) §2)
- `objective` is required; without it the graph refuses to start. `character`/`product` are assumed present; if absent, capture an `absent_reason`.
- Style origin: if a reference is given, seed the whole ReelProfile baseline from its analyzed `VideoProfile`; else the concept LLM proposes from the objective. Record source in `Provenance`.
- Hook is its own node implementing [hook-generator.md](../../../specs/hook-generator.md): LLM picks 1–3 of H1–H12, deterministic rules enforced in code. voice default delivery is `voiceover` (narration). ([ADR.md] ADR-0012)
- Output folder is `outputs/<run_id>/` with `run_id = <concept-slug>-<YYYYMMDD-HHMMSS>`; the ReelProfile file is `ReelProfile-<concept-slug>-<YYYYMMDD-HHMMSS>.json` inside it. plan-stage owns this naming.
- Gates behave as ask (chat default) / pass (`--force-step-pass <step>`) / run (all pass). Same abstraction for every node. ([product-design.md](../../../specs/product-design.md))
- Default locale english/US unless input says otherwise.
- Deterministic layer covered by real assertions; model calls mocked. `pytest -q`, `ruff check src tests`, `ruff format src tests`, `mypy` after a series of changes.

## File structure

```
src/reel_gen_agent/generate/
  run_paths.py          # concept slug + run_id + outputs/<run_id>/ creation
  gates.py              # GateConfig + ask/pass/run resolution (shared gate framework)
  intake.py             # raw input -> Objective, AssetInput(character/product), reference_ref
  text_client.py        # injected LLM client interface (Gemini/Claude behind .env), mockable
  image_client.py       # injected image client interface (Nano Banana / FLUX), mockable
  concept.py            # -> StyleDimensions, narrative_arc, category (LLM, reference-seeded)
  hook.py               # generate_hooks(HookRequest) -> HookSet (hook-generator.md)
  product_analysis.py   # ProductSpec -> affordances + special-feature views (LLM)
  asset_bible.py        # character_assets + product_assets (image) + required-view checklist
  environment.py        # EnvironmentSpec (+ optional reference image)
  templates.py          # narrative_arc templates (UGC, before/after, unboxing, ...)
  storyboard.py         # style_profile + template + affordances + env -> Storyboard (hook=panel0)
  scripting.py          # NarrationSpec(voiceover default) + subtitle_text + MusicSpec (LLM)
  profile_assembly.py   # compose ReelProfile, write ReelProfile-<slug>-<ts>.json
  planning_graph.py     # orchestrator: intake -> ... -> profile_assembly, gates wired
tests/
  test_run_paths.py  test_gates.py  test_intake.py  test_hook.py  test_concept.py
  test_product_analysis.py  test_asset_bible.py  test_environment.py
  test_storyboard.py  test_scripting.py  test_profile_assembly.py  test_planning_graph.py
```

Reused: `analysis/analyze.py` (`analyze_video`) for reference seeding; `generate/schema.py` for all types. The `plan` CLI command is added to `cli.py`.

---

## Milestone 1 — Walking skeleton (stubbed models → valid ReelProfile)

A minimal input produces a schema-valid `ReelProfile-<slug>-<ts>.json` on disk, with every node present but model calls stubbed. This proves the planning graph, gates, and file naming end to end.

### Task 1: run_paths — concept slug, run_id, output folder

**Files:**
- Create: `src/reel_gen_agent/generate/run_paths.py`
- Test: `tests/test_run_paths.py`

**Interfaces:**
- Produces:
  - `slugify(concept: str) -> str` (lowercase, ascii, hyphen-separated, max ~5 words).
  - `make_run_id(concept: str, now: datetime | None = None) -> str` → `<slug>-<YYYYMMDD-HHMMSS>`.
  - `create_run_dir(outputs_root: str, run_id: str) -> Path` → creates and returns `outputs_root/run_id`.
  - `profile_filename(run_id: str) -> str` → `ReelProfile-<run_id>.json`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_paths.py
from datetime import datetime

from reel_gen_agent.generate.run_paths import (
    slugify, make_run_id, create_run_dir, profile_filename,
)


def test_slugify_basic():
    assert slugify("Glow Serum Jelly Reel!") == "glow-serum-jelly-reel"


def test_make_run_id_has_concept_and_timestamp():
    rid = make_run_id("Glow Serum", now=datetime(2026, 7, 1, 10, 10, 10))
    assert rid == "glow-serum-20260701-101010"


def test_create_run_dir_and_profile_filename(tmp_path):
    rid = "glow-serum-20260701-101010"
    d = create_run_dir(str(tmp_path), rid)
    assert d.is_dir()
    assert profile_filename(rid) == "ReelProfile-glow-serum-20260701-101010.json"
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_run_paths.py -v` → FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/run_paths.py
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
```

- [ ] **Step 4: Run to verify it passes** — `uv run pytest tests/test_run_paths.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/run_paths.py tests/test_run_paths.py
git commit -m "feat(plan): run_id naming and output folder helpers"
```

### Task 2: gates — ask/pass/run framework

**Files:**
- Create: `src/reel_gen_agent/generate/gates.py`
- Test: `tests/test_gates.py`

**Interfaces:**
- Produces:
  - `GateConfig(mode: str = "run", force_pass: set[str] = ...)` — `mode` in {`ask`, `run`}; `force_pass` holds step names.
  - `resolve_gate(config: GateConfig, step: str, ask_fn) -> str` returns `"pass"` when run mode or step in force_pass; otherwise calls `ask_fn()` and returns its decision (`"confirm"`/`"edit"`). `ask_fn` is injected so tests need no I/O.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gates.py
from reel_gen_agent.generate.gates import GateConfig, resolve_gate


def test_run_mode_auto_passes_without_asking():
    called = []
    out = resolve_gate(GateConfig(mode="run"), "hook", lambda: called.append(1) or "confirm")
    assert out == "pass"
    assert called == []


def test_force_pass_skips_one_step():
    cfg = GateConfig(mode="ask", force_pass={"storyboard"})
    assert resolve_gate(cfg, "storyboard", lambda: "confirm") == "pass"


def test_ask_mode_calls_ask_fn():
    cfg = GateConfig(mode="ask")
    assert resolve_gate(cfg, "hook", lambda: "edit") == "edit"
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_gates.py -v` → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/gates.py
"""게이트 일반화: ask(챗 확인/수정) / pass(force-step-pass) / run(전부 통과).

모든 중요한 노드 뒤에 같은 추상을 둔다([ADR.md] ADR-0007). ask_fn을 주입해 UI와 분리한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class GateConfig:
    mode: str = "run"  # ask / run
    force_pass: set[str] = field(default_factory=set)


def resolve_gate(config: GateConfig, step: str, ask_fn: Callable[[], str]) -> str:
    if config.mode == "run" or step in config.force_pass:
        return "pass"
    return ask_fn()
```

- [ ] **Step 4: Run to verify it passes** — `uv run pytest tests/test_gates.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/gates.py tests/test_gates.py
git commit -m "feat(plan): ask/pass/run gate framework"
```

### Task 3: intake — input discrimination

**Files:**
- Create: `src/reel_gen_agent/generate/intake.py`
- Test: `tests/test_intake.py`

**Interfaces:**
- Produces: `intake(raw: str) -> IntakeResult` where `IntakeResult` is a small dataclass with `objective: Objective | None`, `character: AssetInput`, `product: AssetInput`, `reference_ref: str | None`, `raw_brief: str | None`. Rules from [product-design.md]: existing `.json` path → load as ReelProfile (skip; handled in CLI); single token that is a path/URL → single asset (video→reference, image→character/product by labels); multi-token natural language → text brief, extract URLs/paths, classify by labels ("제품:", "레퍼런스 영상:", "캐릭터:") else by media kind. Missing character/product → `present=False`, `absent_reason=None` (filled by ask later). Defaults language en/US.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_intake.py
from reel_gen_agent.generate.intake import intake


def test_text_brief_extracts_labeled_assets():
    r = intake("발랄한 15초 언박싱 릴. 제품: https://b/serum 레퍼런스 영상: ./ref.mp4")
    assert r.objective is not None
    assert r.product.present and r.product.source == "https://b/serum"
    assert r.reference_ref == "./ref.mp4"
    assert r.raw_brief is not None


def test_absent_product_is_flagged_not_filled():
    r = intake("브랜드 무드 영상, 제품 없이 분위기만")
    assert r.product.present is False
    assert r.product.absent_reason is None  # ask 단계가 채운다
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_intake.py -v` → FAIL.

- [ ] **Step 3: Write minimal implementation** (concrete extraction; keep heuristics simple and tested)

```python
# src/reel_gen_agent/generate/intake.py
"""입력 판별. 텍스트 브리프/단일 에셋/JSON 경로를 Objective+AssetInput으로 푼다.

판별 규칙 정본은 specs/product-design.md. 라벨 우선, 없으면 미디어 종류로 추정.
기본 로케일은 영어·미국.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schema import AssetInput, Objective

_URL = re.compile(r"https?://\S+")
_PATH = re.compile(r"\.?/?\S+\.(?:mp4|mov|jpg|jpeg|png|webp)", re.IGNORECASE)
_VIDEO_EXT = (".mp4", ".mov")


@dataclass
class IntakeResult:
    objective: Objective | None
    character: AssetInput
    product: AssetInput
    reference_ref: str | None
    raw_brief: str | None


def _labeled(raw: str, labels: list[str]) -> str | None:
    for label in labels:
        m = re.search(rf"{label}\s*[:：]\s*(\S+)", raw)
        if m:
            return m.group(1)
    return None


def intake(raw: str) -> IntakeResult:
    product_src = _labeled(raw, ["제품", "product"])
    character_src = _labeled(raw, ["캐릭터", "character", "모델"])
    ref_src = _labeled(raw, ["레퍼런스 영상", "레퍼런스", "reference"])
    if ref_src is None:
        for tok in _URL.findall(raw) + _PATH.findall(raw):
            if tok.lower().endswith(_VIDEO_EXT):
                ref_src = tok
                break
    product = AssetInput(kind="product", source=product_src, present=product_src is not None)
    character = AssetInput(kind="character", source=character_src, present=character_src is not None)
    objective = Objective(goal=raw.strip()) if raw.strip() else None
    return IntakeResult(
        objective=objective,
        character=character,
        product=product,
        reference_ref=ref_src,
        raw_brief=raw.strip() or None,
    )
```

- [ ] **Step 4: Run to verify it passes** — `uv run pytest tests/test_intake.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/intake.py tests/test_intake.py
git commit -m "feat(plan): intake input discrimination (objective + assets + reference)"
```

### Task 4: hook — generate_hooks with enforced deterministic rules

**Files:**
- Create: `src/reel_gen_agent/generate/text_client.py`, `src/reel_gen_agent/generate/hook.py`
- Test: `tests/test_hook.py`

**Interfaces:**
- Consumes: `HookRequest`, `HOOK_TYPES`, `CATEGORY_HOOK_DEFAULTS` (schema.py).
- Produces:
  - `text_client.TextClient` (Protocol): `complete(prompt: str, *, temperature: float = 0.9) -> str`. A `StubTextClient(responses)` for tests.
  - `hook.generate_hooks(request: HookRequest, client: TextClient) -> HookSet`. Code enforces (per [hook-generator.md]): window length (`duration_sec>=10` → (0,3); else (0, min(2, dur*0.2))); reject unknown `hook_type`; low-product-fit type requires non-empty `bridge`; with `count>=2` include at least one question + one command variant; if `no_text_visual` then headline/bottom None and `visual_direction` non-empty.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hook.py
import json

import pytest

from reel_gen_agent.generate.hook import generate_hooks
from reel_gen_agent.generate.text_client import StubTextClient
from reel_gen_agent.generate.schema import HookRequest, ProductSpec


def _client(cands):
    return StubTextClient([json.dumps({"candidates": cands})])


def test_window_is_three_seconds_for_long_video():
    cands = [
        {"hook_type": "H1", "headline": "Glow", "visual_direction": "macro", "bridge": "serum", "variant": "question"},
        {"hook_type": "H1", "headline": "Glow now", "visual_direction": "macro", "bridge": "serum", "variant": "command"},
    ]
    hs = generate_hooks(HookRequest(product=ProductSpec(name="serum"), duration_sec=18, count=2), _client(cands))
    assert hs.candidates[0].window_sec == (0.0, 3.0)


def test_window_compressed_for_short_video():
    cands = [{"hook_type": "H1", "headline": "x", "visual_direction": "v", "bridge": "b", "variant": "question"},
             {"hook_type": "H1", "headline": "y", "visual_direction": "v", "bridge": "b", "variant": "command"}]
    hs = generate_hooks(HookRequest(product=ProductSpec(name="s"), duration_sec=8, count=2), _client(cands))
    assert hs.candidates[0].window_sec == (0.0, pytest.approx(1.6))


def test_unknown_hook_type_rejected():
    cands = [{"hook_type": "H99", "headline": "x", "visual_direction": "v", "bridge": "b"}]
    with pytest.raises(ValueError):
        generate_hooks(HookRequest(product=ProductSpec(name="s"), count=1), _client(cands))


def test_low_fit_requires_bridge():
    cands = [{"hook_type": "H12", "headline": "A or B?", "visual_direction": "v", "bridge": ""}]
    with pytest.raises(ValueError):
        generate_hooks(HookRequest(product=ProductSpec(name="s"), count=1), _client(cands))
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_hook.py -v` → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/text_client.py
"""기획·카피 LLM 클라이언트 인터페이스. 실제 백엔드(Gemini/Claude)는 .env로 고른다.

테스트는 StubTextClient로 호출을 막는다([ai-model-records.md] §2, TEXT_MODEL_PRIORITY).
"""

from __future__ import annotations

from typing import Protocol


class TextClient(Protocol):
    def complete(self, prompt: str, *, temperature: float = 0.9) -> str: ...


class StubTextClient:
    """정해 둔 응답을 순서대로 돌려주는 테스트용 클라이언트."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def complete(self, prompt: str, *, temperature: float = 0.9) -> str:
        return self._responses.pop(0)
```

```python
# src/reel_gen_agent/generate/hook.py
"""후크 생성기. 계약 정본 specs/hook-generator.md.

LLM이 유형·문구를 비결정적으로 내고, 코드가 결정론 규칙(윈도·유형 유효성·낮은 적합도
가드·A/B 변형·텍스트/비주얼 정합)을 강제한다.
"""

from __future__ import annotations

import json

from .schema import HOOK_TYPES, HookCandidate, HookRequest, HookSet
from .text_client import TextClient

_PROMPT = (
    "역할: 20~30초 세로 뷰티 숏폼의 첫 1~3초 후크 {count}개를 생성한다.\n"
    "제품: {product}. 카테고리: {category}. 톤: {tone}.\n"
    "출력: JSON {{\"candidates\": [{{hook_type, headline, bottom_caption, "
    "no_text_visual, visual_direction, opening_beat, bridge, variant, rationale}}]}}.\n"
    "유형은 H1~H12 중에서 고른다. count>=2면 질문형·명령형을 섞는다."
)


def _window(duration_sec: float) -> tuple[float, float]:
    if duration_sec >= 10:
        return (0.0, 3.0)
    return (0.0, min(2.0, duration_sec * 0.2))


def generate_hooks(request: HookRequest, client: TextClient) -> HookSet:
    prompt = _PROMPT.format(
        count=request.count,
        product=request.product.name,
        category=request.category or "auto",
        tone=", ".join(request.tone) or "auto",
    )
    raw = client.complete(prompt, temperature=0.9)
    data = json.loads(raw)
    window = _window(request.duration_sec)
    candidates: list[HookCandidate] = []
    for c in data["candidates"]:
        cand = HookCandidate(**c)  # validator가 hook_type을 검증한다
        cand.window_sec = window
        fit = HOOK_TYPES[cand.hook_type]["product_fit"]
        if fit == "low" and not (cand.bridge or "").strip():
            raise ValueError(f"low-fit hook {cand.hook_type} requires non-empty bridge")
        if cand.no_text_visual:
            cand.headline = None
            cand.bottom_caption = None
            if not cand.visual_direction.strip():
                raise ValueError("no_text_visual requires visual_direction")
        candidates.append(cand)
    if request.count >= 2:
        variants = {c.variant for c in candidates}
        if not ({"question", "command"} <= variants):
            raise ValueError("count>=2 must include a question and a command variant")
    return HookSet(candidates=candidates, request=request)
```

- [ ] **Step 4: Run to verify it passes** — `uv run pytest tests/test_hook.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/text_client.py src/reel_gen_agent/generate/hook.py tests/test_hook.py
git commit -m "feat(plan): hook generator with enforced deterministic rules (hook-generator.md)"
```

### Task 5: profile_assembly — compose and write ReelProfile

**Files:**
- Create: `src/reel_gen_agent/generate/profile_assembly.py`
- Test: `tests/test_profile_assembly.py`

**Interfaces:**
- Consumes: all node outputs (`Objective`, `ProductSpec`, `ModelSpec`, `StyleDimensions`, `narrative_arc`, `AssetBible`, `Storyboard`, `NarrationSpec`, `MusicSpec`, `Provenance`).
- Produces: `assemble_profile(parts: dict) -> ReelProfile` and `write_profile(profile: ReelProfile, out_dir: Path, run_id: str) -> Path` (writes `ReelProfile-<run_id>.json`, returns path).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profile_assembly.py
from reel_gen_agent.generate.profile_assembly import assemble_profile, write_profile
from reel_gen_agent.generate.run_paths import profile_filename
from reel_gen_agent.generate.schema import Objective, ProductSpec, ReelProfile


def test_assemble_and_write_roundtrips(tmp_path):
    profile = assemble_profile({
        "objective": Objective(goal="glow reel"),
        "product": ProductSpec(name="serum"),
    })
    assert isinstance(profile, ReelProfile)
    p = write_profile(profile, tmp_path, "glow-20260701-101010")
    assert p.name == profile_filename("glow-20260701-101010")
    restored = ReelProfile.model_validate_json(p.read_text(encoding="utf-8"))
    assert restored == profile
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_profile_assembly.py -v` → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/profile_assembly.py
"""profile_assembly 노드: 기획 부산물을 ReelProfile로 동결하고 파일로 쓴다.

같은 ReelProfile은 유사 영상을 만든다(execute의 입력). 파일명은 run_paths 규약을 따른다.
"""

from __future__ import annotations

from pathlib import Path

from .run_paths import profile_filename
from .schema import Objective, ProductSpec, ReelProfile


def assemble_profile(parts: dict) -> ReelProfile:
    objective: Objective = parts["objective"]
    product: ProductSpec = parts["product"]
    return ReelProfile(
        objective=objective,
        product=product,
        character=parts.get("character") or ReelProfile.model_fields["character"].default_factory(),
        style=parts.get("style") or ReelProfile.model_fields["style"].default_factory(),
        narrative_arc=parts.get("narrative_arc", []),
        asset_bible=parts.get("asset_bible") or ReelProfile.model_fields["asset_bible"].default_factory(),
        storyboard=parts.get("storyboard") or ReelProfile.model_fields["storyboard"].default_factory(),
        narration=parts.get("narration") or ReelProfile.model_fields["narration"].default_factory(),
        music=parts.get("music") or ReelProfile.model_fields["music"].default_factory(),
        provenance=parts.get("provenance") or ReelProfile.model_fields["provenance"].default_factory(),
    )


def write_profile(profile: ReelProfile, out_dir: Path, run_id: str) -> Path:
    path = Path(out_dir) / profile_filename(run_id)
    path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return path
```

(If accessing `model_fields[...].default_factory()` reads awkwardly, build defaults by constructing the sub-models directly, e.g. `parts.get("style") or StyleDimensions()`. Adjust imports accordingly and keep the test green.)

- [ ] **Step 4: Run to verify it passes** — `uv run pytest tests/test_profile_assembly.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/profile_assembly.py tests/test_profile_assembly.py
git commit -m "feat(plan): profile_assembly composes and writes ReelProfile json"
```

### Task 6: planning orchestrator + plan CLI (skeleton end-to-end)

**Files:**
- Create: `src/reel_gen_agent/generate/planning_graph.py`
- Modify: `src/reel_gen_agent/cli.py` (add `plan` command)
- Test: `tests/test_planning_graph.py`

**Interfaces:**
- Consumes: intake, hook (stub client), run_paths, profile_assembly, gates.
- Produces: `run_planning(raw: str, outputs_root: str, *, gate: GateConfig, text_client: TextClient | None = None) -> Path`. Skeleton order: intake → (reference seed skipped if none) → minimal concept (defaults if no client) → hook (if client) → minimal asset_bible/environment/storyboard/scripting defaults → profile_assembly → write file. Returns the ReelProfile path. `objective is None` raises a clear error.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_planning_graph.py
import json

import pytest

from reel_gen_agent.generate.planning_graph import run_planning
from reel_gen_agent.generate.gates import GateConfig
from reel_gen_agent.generate.text_client import StubTextClient
from reel_gen_agent.generate.schema import ReelProfile


def test_run_planning_writes_valid_reel_profile(tmp_path):
    cands = {"candidates": [
        {"hook_type": "H1", "headline": "Glow", "visual_direction": "macro", "bridge": "serum", "variant": "question"},
        {"hook_type": "H1", "headline": "Glow now", "visual_direction": "macro", "bridge": "serum", "variant": "command"},
    ]}
    client = StubTextClient([json.dumps(cands)])
    path = run_planning(
        "발랄한 15초 언박싱 릴. 제품: https://b/serum",
        str(tmp_path / "outputs"),
        gate=GateConfig(mode="run"),
        text_client=client,
    )
    assert path.name.startswith("ReelProfile-")
    profile = ReelProfile.model_validate_json(path.read_text(encoding="utf-8"))
    assert profile.objective.goal


def test_missing_objective_raises(tmp_path):
    with pytest.raises(ValueError):
        run_planning("", str(tmp_path / "outputs"), gate=GateConfig(mode="run"))
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_planning_graph.py -v` → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/planning_graph.py
"""plan 오케스트레이터(워킹 스켈레톤). 그래프 위상은 정적, 게이트는 일반화.

흐름: intake -> (concept/hook/assets/env/storyboard/scripting) -> profile_assembly -> write.
지금은 순차 함수 + 스텁 모델이다. LangGraph 노드/인터럽트와 실제 LLM·이미지 호출은
Milestone 2에서 같은 인터페이스 뒤에 붙인다.
"""

from __future__ import annotations

from pathlib import Path

from .gates import GateConfig
from .intake import intake
from .profile_assembly import assemble_profile, write_profile
from .run_paths import create_run_dir, make_run_id
from .schema import HookRequest, Provenance, StyleDimensions
from .text_client import TextClient


def run_planning(
    raw: str,
    outputs_root: str,
    *,
    gate: GateConfig,
    text_client: TextClient | None = None,
) -> Path:
    result = intake(raw)
    if result.objective is None:
        raise ValueError("objective(영상 목적)는 필수다. 입력이 비었다.")

    product = __import__("reel_gen_agent.generate.schema", fromlist=["ProductSpec"]).ProductSpec(
        name=(result.product.source or "product")
    )
    style = StyleDimensions()
    provenance = Provenance(
        style_source="reference" if result.reference_ref else "llm",
        reference_ref=result.reference_ref,
    )

    if text_client is not None:
        from .hook import generate_hooks

        hooks = generate_hooks(
            HookRequest(product=product, tone=style.tone, duration_sec=18.0, count=2),
            text_client,
        )
        if hooks.candidates:
            style.hook = hooks.candidates[0]

    profile = assemble_profile({
        "objective": result.objective,
        "product": product,
        "style": style,
        "provenance": provenance,
    })

    run_id = make_run_id(result.objective.goal)
    out_dir = create_run_dir(outputs_root, run_id)
    return write_profile(profile, out_dir, run_id)
```

(Replace the `__import__` shim with a normal `from .schema import ProductSpec` at module top — it is shown inline only to keep the example self-contained. Use the clean import.)

Then the CLI:

```python
# add to src/reel_gen_agent/cli.py
from .generate.gates import GateConfig
from .generate.planning_graph import run_planning


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
```

- [ ] **Step 4: Run to verify it passes** — `uv run pytest tests/test_planning_graph.py -v` → PASS. Then `uv run pytest -q` (full), `uv run ruff check src tests && uv run mypy`.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/planning_graph.py src/reel_gen_agent/cli.py tests/test_planning_graph.py
git commit -m "feat(plan): planning orchestrator and plan CLI (walking skeleton)"
```

**Milestone 1 done:** `uv run reel-gen plan "<brief>" --yes` writes a schema-valid `ReelProfile-<slug>-<ts>.json` under `outputs/<run_id>/` with stubbed models.

---

## Milestone 2 — Deepen (real nodes behind the same interfaces)

Same TDD rhythm. Mock all model calls; key-absent paths fall back to deterministic defaults, never crash. Each node is wired into `planning_graph.py` with a gate via `resolve_gate`.

### Task 7: reference_analysis seeding
- **Files:** Modify `planning_graph.py`; create `reference_seed.py`.
- **Add:** when `reference_ref` present, call `analyze_video` (analysis layer) → `VideoProfile`, map it to a baseline `StyleDimensions` (tone, pacing, cut_rhythm.source="reference"), `MusicSpec`, and seed panel count/timing for storyboard. Set `Provenance.style_source="reference"`.
- **Test:** mock `analyze_video` to return a fixed VideoProfile; assert StyleDimensions/MusicSpec carry the seeded values and `cut_rhythm.source == "reference"`.
- **Contract:** [information-schema.md](../../../specs/information-schema.md) "레퍼런스 시딩 범위".

### Task 8: concept node
- **Files:** Create `concept.py`; wire into graph with `gate: concept`-less (concept feeds hook); add `category` inference.
- **Interface:** `build_concept(objective, product, style_profile|None, client) -> ConceptOut(style: StyleDimensions, narrative_arc: list[str], category: str)`. Reference-seeded when style_profile given, else LLM from objective.
- **Test:** stub client returns JSON; assert 5 dimensions populated, category chosen from `CATEGORY_HOOK_DEFAULTS` keys, narrative_arc non-empty.

### Task 9: product_analysis node
- **Files:** Create `product_analysis.py`.
- **Interface:** `analyze_product(product, client) -> ProductSpec` with `affordances` filled and special-feature notes for catalog views.
- **Test:** stub client; assert `affordances` non-empty and feature notes returned.

### Task 10: asset_bible node (image client)
- **Files:** Create `image_client.py` (Protocol `generate(prompt, refs, out_path) -> str`, `StubImageClient`), `asset_bible.py`.
- **Interface:** `build_asset_bible(profile_parts, image_client, out_dir) -> AssetBible`. Builds character required views [face_closeup, expression_variation, full_body, left_face, right_face] and product required views [front, sides_top, in_box, special_function] as `AssetView` entries; marks `satisfied` when an image path is produced. Honors absent character/product (skip, record intent).
- **Test:** stub image client returns fake paths; assert all required `AssetView`s present and `satisfied=True`; absent product → product views empty and reason recorded.
- **Contract:** [workflows.md] asset nodes; nano banana sheet + checklist.

### Task 11: environment node
- **Files:** Create `environment.py`.
- **Interface:** `build_environment(concept, client, image_client) -> EnvironmentSpec`. Always fills text; sets `needs_image` and generates a reference image only when text is judged insufficient.
- **Test:** stub clients; assert text fields filled; when `needs_image=True` an image path is set, else None.

### Task 12: templates + storyboard node
- **Files:** Create `templates.py` (named narrative_arc templates with beat/shot rules), `storyboard.py`.
- **Interface:** `build_storyboard(style, narrative_arc, affordances, environment, hook, meta, style_profile|None) -> Storyboard`. Panel count/timing seeded from style_profile cut data (fallback: derive from meta.duration_sec and pacing). Panel 0 is the hook (`beat="hook"`, `t_start=0`, `subtitle_text=hook.headline`). Inject platform safe-zone/length constraints. Each panel sets `environment_lock=True`.
- **Test:** with a fast-cut style_profile vs slow-cut, assert different panel counts; assert panel 0 is the hook; assert total timing ≤ meta.duration_sec.
- **Contract:** [pipeline-design.md](../../../docs/pipeline-design.md) seeding + platform constraints.

### Task 13: scripting node
- **Files:** Create `scripting.py`.
- **Interface:** `build_scripting(storyboard, style, character, client) -> tuple[NarrationSpec, MusicSpec, Storyboard]`. NarrationSpec `delivery="voiceover"` default, `voice` derived from `ModelSpec`; subtitle text written per `SubtitleSpec.density` (keyword vs full); MusicSpec style/tempo aligned to cut_rhythm. Returns storyboard with `subtitle_text` filled.
- **Test:** stub client; assert delivery default voiceover, voice.from_character True, panel subtitle_text filled, MusicSpec.tempo set.
- **Contract:** [ADR.md] ADR-0012, [information-schema.md] NarrationSpec.

### Task 14: full graph wiring + gates + confirm
- **Files:** Modify `planning_graph.py` to a LangGraph `StateGraph` with one node per stage and a `resolve_gate` interrupt after hook, asset_bible, storyboard, scripting, and a final `confirm` gate before writing. `--force-step-pass` plumbs into `GateConfig.force_pass`.
- **Test:** run mode passes all; ask mode with a stub `ask_fn` returning "confirm" advances; force_pass set skips the named gate.
- **Contract:** [product-design.md] gate flags; [workflows.md] Planning diagram.

### Task 15: missing-asset intent capture (ask_intent)
- **Files:** Modify `intake.py`/`planning_graph.py` to ask why a missing character/product is absent (chat) or fill a default intent (run), and route eligible narrative templates accordingly.
- **Test:** run mode fills default `absent_reason`; the chosen narrative_arc respects "no character → product-only" template eligibility.

---

## Self-review notes

- Spec coverage: intake (T3,T15), reference seeding (T7), concept+5 dims (T8), hook node (T4), product_analysis (T9), asset_bible+required views (T10), environment (T11), storyboard+seeding+platform (T12), scripting+narration/subtitle/music (T13), profile_assembly+naming (T1,T5), gates+confirm (T2,T14), ReelProfile output (T5,T6) — all mapped.
- Skeleton (T1-T6) writes a valid ReelProfile with stubbed models; real LLM/image nodes (T7-T13) are mocked in tests via `TextClient`/`ImageClient` stubs.
- Type consistency: `TextClient.complete` and `ImageClient.generate` signatures are fixed and reused across nodes; all data types come from the shared `generate/schema.py` (`HookSet`/`StyleDimensions`/`ReelProfile`/…), not redefined. `generate_hooks(request, client)` arg order matches every call site.
- Before T7, confirm `analyze_video` signature/return (`analysis/analyze.py`) and `VideoProfile` field names to map the reference seed correctly.
- The `gates.py` framework built here is the shared gate abstraction; the execute stage may import it after the branches merge (it does not need it for its skeleton).
