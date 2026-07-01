# execute --replan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `execute --replan`, which re-rolls the narrative (hook <-> storyboard, narration, music) of an existing ReelProfile from a fresh hook while reusing the frozen identity assets, writes a new `ReelProfile-<new-keyword>.json` into a new run folder, and runs production on it.

**Architecture:** A focused LangGraph sub-graph (`replan_graph.py`) reuses the existing narrative plan nodes (`_hook_node`, `_storyboard_node`, `_route_after_storyboard`, `_narration_node`, `_music_node`) with no image work. An orchestrator `run_replan()` seeds that graph from a loaded ReelProfile, then handles paths: it derives a new run id from the new hook, copies the identity asset images into a new plan dir, regenerates `key_visual`, assembles and writes the new profile. The CLI `execute --replan` flag calls `run_replan()` then produces the new profile.

**Tech Stack:** Python 3.10+, LangGraph, pydantic, typer, pytest. Runs inside the project `.venv` (use `uv run` / `.venv/bin/...`).

## Global Constraints

- Analysis and generation communicate only through the pydantic schemas; replan adds no schema fields and no new external backend.
- No hardcoded style constants that should be parameters; carry values from the loaded profile.
- Python 3.10+, four-space indent, PEP 8: `snake_case` functions/vars, `PascalCase` classes. Python modules are `snake_case`.
- Comments explain the "why". Public functions get docstrings. Files end with a trailing newline, UTF-8.
- No brand names or assignment/job context anywhere in this repo (code, docs, tests, commits).
- Run everything inside `.venv`. Typecheck (`mypy`) and `ruff check` + `pytest -q` after changes; prefer the specific test while iterating.
- Tests are independent and generate their own data; mock external model calls (text/image clients).

---

### Task 1: replan sub-graph (`replan_graph.py`)

**Files:**
- Create: `src/reel_gen_agent/generate/replan_graph.py`
- Test: `tests/test_replan_graph.py`

**Interfaces:**
- Consumes (from `plan_graph.py`, unchanged): `_hook_node`, `_storyboard_node`, `_route_after_storyboard`, `_narration_node`, `_music_node`, `MAX_HOOK_ATTEMPTS`, `PlanState`.
- Produces: `build_replan_graph()` — compiles and returns a LangGraph whose `.invoke(state)` runs `hook -> storyboard -(route)-> [hook | narration] -> narration -> music -> END` and returns a final state dict containing `storyboard`, `narration`, `music`, `style`, `narrative_arc`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_replan_graph.py
"""replan 서브그래프: 정체성 노드 없이 narrative(hook->storyboard->narration->music)만 돈다."""

from __future__ import annotations

from reel_gen_agent.generate.replan_graph import build_replan_graph
from reel_gen_agent.generate.schema import (
    EnvironmentSpec,
    InputMeta,
    ModelSpec,
    MusicSpec,
    Objective,
    ProductSpec,
    StyleDimensions,
)
from reel_gen_agent.generate.trace import Tracer


def _seed_state() -> dict:
    return {
        "text_client": None,  # 결정론 경로(LLM 없이 템플릿)
        "image_client": None,
        "tracer": Tracer(session_id="t-replan", run_id="t-replan"),
        "objective": Objective(goal="show a serum glow routine"),
        "product": ProductSpec(name="serum"),
        "meta": InputMeta(),
        "style": StyleDimensions(),
        "character": ModelSpec(age="early 20s", gender="female", look="radiant creator"),
        "environment": EnvironmentSpec(location="bright indoor vanity"),
        "music": MusicSpec(),
        "delivery": "voiceover",
        "ref_voice_tone": "",
        "ref_voice_pace": "",
        "ref_hook": None,
        "cut_count": 3,
        "hook_attempts": 0,
        "hook_feedback": "",
        "style_feedback": "",
    }


def test_replan_graph_produces_narrative_only():
    graph = build_replan_graph()
    final = graph.invoke(_seed_state())
    # narrative 산출물이 모두 채워진다.
    assert final["storyboard"].panels
    assert final["narration"] is not None
    assert final["music"] is not None
    assert "narrative_arc" in final
    # 정체성은 그래프가 건드리지 않는다(들어온 그대로 나온다).
    assert final["product"].name == "serum"
    assert final["character"].look == "radiant creator"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_replan_graph.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'reel_gen_agent.generate.replan_graph'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/replan_graph.py
"""replan 페이즈 LangGraph. 기존 ReelProfile에서 narrative만 다시 전개한다(specs/replan.md).

흐름: hook <-> storyboard(핑퐁) -> narration -> music -> END. plan 그래프의 narrative
노드를 그대로 재사용하며, 정체성 노드(product/character/environment)와 이미지 생성·
write는 돌지 않는다. 새 폴더·에셋 복사·key_visual 재생성·프로필 조립은 오케스트레이터
(run_replan)가 맡는다. 새 훅의 키워드는 그래프 실행 후에야 정해지기 때문이다.
"""

from __future__ import annotations

from .plan_graph import (
    PlanState,
    _hook_node,
    _music_node,
    _narration_node,
    _route_after_storyboard,
    _storyboard_node,
)


def build_replan_graph():
    """replan 페이즈 StateGraph를 컴파일한다(narrative 노드만)."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(PlanState)
    for name, fn in [
        ("hook", _hook_node),
        ("storyboard", _storyboard_node),
        ("narration", _narration_node),
        ("music", _music_node),
    ]:
        g.add_node(name, fn)
    g.add_edge(START, "hook")
    g.add_edge("hook", "storyboard")
    g.add_conditional_edges(
        "storyboard", _route_after_storyboard, {"hook": "hook", "narration": "narration"}
    )
    g.add_edge("narration", "music")
    g.add_edge("music", END)
    return g.compile()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_replan_graph.py -q`
Expected: PASS

- [ ] **Step 5: Typecheck, lint, commit**

Run: `.venv/bin/mypy src/reel_gen_agent/generate/replan_graph.py && .venv/bin/ruff check src/reel_gen_agent/generate/replan_graph.py tests/test_replan_graph.py`
Expected: no errors

```bash
git add src/reel_gen_agent/generate/replan_graph.py tests/test_replan_graph.py
git commit -m "feat(generate): add replan narrative sub-graph"
```

---

### Task 2: `run_replan()` orchestrator

**Files:**
- Modify: `src/reel_gen_agent/generate/planning_graph.py` (add `run_replan`)
- Test: `tests/test_run_replan.py`

**Interfaces:**
- Consumes: `build_replan_graph()` (Task 1); `assemble_profile`, `write_profile` from `profile_assembly.py`; `build_key_visual` from `asset_bible.py` (`build_key_visual(profile, image_client, out_dir, character_image=None, product_image=None) -> str | None`); `make_run_id`, `create_run_dir` from `run_paths.py`; `Tracer` from `trace.py`; schemas `ReelProfile`, `AssetBible`.
- Produces: `run_replan(profile_path: str, outputs_root: str, *, text_client: TextClient | None = None, image_client: ImageClient | None = None) -> Path` — returns the new ReelProfile path under `outputs/<new_run_id>/plan/`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_replan.py
"""run_replan: 정체성 고정 + narrative 재전개 + 새 폴더/에셋 복사/ key_visual 폴백."""

from __future__ import annotations

from pathlib import Path

from reel_gen_agent.generate.planning_graph import run_replan
from reel_gen_agent.generate.profile_assembly import write_profile
from reel_gen_agent.generate.schema import (
    AssetBible,
    AssetView,
    CharacterProfile,
    EnvironmentSpec,
    InputMeta,
    ModelSpec,
    MusicSpec,
    Objective,
    ProductProfile,
    ProductSpec,
    ReelProfile,
    Storyboard,
    StoryboardPanel,
    StyleDimensions,
)


def _write_original(tmp_path: Path) -> str:
    """가짜 원본 run 폴더(outputs/<run>/plan/)에 ReelProfile + 정체성 에셋 파일을 만든다."""
    plan_dir = tmp_path / "orig-run" / "plan"
    plan_dir.mkdir(parents=True)
    for name in ("char_key.png", "char_sheet.png", "prod_hero.png", "env_ref.png", "key_visual.png"):
        (plan_dir / name).write_bytes(b"PNG-STUB")
    profile = ReelProfile(
        objective=Objective(goal="show a gentle serum glow routine"),
        product=ProductSpec(name="hydra serum"),
        character=ModelSpec(age="early 20s", gender="female", look="radiant creator"),
        meta=InputMeta(),
        style=StyleDimensions(),
        narrative_arc=["hook", "use", "result"],
        asset_bible=AssetBible(
            character=CharacterProfile(
                name="creator",
                key_shot_image="char_key.png",
                sheet_image="char_sheet.png",
                views=[AssetView(name="face", image="char_sheet.png")],
            ),
            product=ProductProfile(name="hydra serum", hero_image="prod_hero.png"),
            environment=EnvironmentSpec(location="bright vanity", reference_image="env_ref.png"),
            key_visual="key_visual.png",
        ),
        storyboard=Storyboard(panels=[StoryboardPanel(index=i) for i in range(3)]),
        music=MusicSpec(),
    )
    return str(write_profile(profile, plan_dir, "orig-run"))


def test_run_replan_locks_identity_and_makes_new_folder(tmp_path):
    original = _write_original(tmp_path)
    outputs_root = str(tmp_path)

    # text/image 클라이언트 없이(결정론 + key_visual 폴백) 실행.
    new_path = run_replan(original, outputs_root, text_client=None, image_client=None)

    new_plan_dir = new_path.parent
    # 새 폴더가 원본과 다르고 실제로 생겼다.
    assert new_plan_dir.exists()
    assert new_plan_dir.resolve() != Path(original).parent.resolve()
    # 정체성 에셋 이미지가 새 plan 폴더로 복사됐다.
    assert (new_plan_dir / "char_key.png").exists()
    assert (new_plan_dir / "prod_hero.png").exists()
    assert (new_plan_dir / "env_ref.png").exists()
    # key_visual은 image_client 없으므로 원본을 복사해 폴백.
    assert (new_plan_dir / "key_visual.png").exists()

    new_profile = ReelProfile.model_validate_json(new_path.read_text(encoding="utf-8"))
    # 정체성 고정: 목적/제품/캐릭터는 원본과 동일.
    assert new_profile.objective.goal == "show a gentle serum glow routine"
    assert new_profile.product.name == "hydra serum"
    assert new_profile.character.look == "radiant creator"
    # narrative 산출물이 존재하고, 재기획 흔적이 남는다.
    assert new_profile.storyboard.panels
    assert new_profile.provenance.seeds.get("replanned_from") == original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_run_replan.py -q`
Expected: FAIL with `ImportError: cannot import name 'run_replan'`

- [ ] **Step 3: Write minimal implementation**

Add to `src/reel_gen_agent/generate/planning_graph.py` (new imports at top, new function below `run_planning`):

```python
# add to the imports block at the top of planning_graph.py
import shutil

from .asset_bible import build_key_visual
from .profile_assembly import assemble_profile, write_profile
from .replan_graph import build_replan_graph
from .run_paths import create_run_dir, make_run_id
from .schema import AssetBible, ReelProfile
from .trace import Tracer
```

```python
def _copy_identity_assets(bible: AssetBible, src_dir: Path, dst_dir: Path) -> None:
    """정체성 에셋 이미지 파일(캐릭터·제품·환경)을 원본 plan 폴더에서 새 폴더로 복사한다.

    key_visual은 여기서 복사하지 않는다(새 훅에 맞춰 재생성하거나, 실패 시 폴백에서 복사).
    파일이 없으면 조용히 건너뛴다(상대 파일명은 그대로라 새 프로필에서 해소된다).
    """
    names: list[str | None] = [
        bible.character.sheet_image,
        bible.character.key_shot_image,
        bible.product.sheet_image,
        bible.product.hero_image,
        bible.environment.reference_image,
    ]
    names += [v.image for v in bible.character.views]
    names += [v.image for v in bible.product.views]
    for rel in names:
        if not rel:
            continue
        src = src_dir / rel
        if src.exists():
            shutil.copy2(src, dst_dir / rel)


def run_replan(
    profile_path: str,
    outputs_root: str,
    *,
    text_client: TextClient | None = None,
    image_client: ImageClient | None = None,
) -> Path:
    """기존 ReelProfile을 새 훅으로 재전개해 새 폴더에 새 ReelProfile을 쓴다(specs/replan.md).

    정체성(objective/product/character/meta + 캐릭터·제품·환경 에셋)은 고정하고, narrative
    (hook<->storyboard, narration, music)만 다시 만든다. key_visual은 새 훅에 맞춰 재생성하되
    image_client가 없거나 실패하면 원본을 복사해 폴백한다. 산출 폴더는 새 훅 키워드로 명명한다.
    """
    src_profile = ReelProfile.model_validate_json(Path(profile_path).read_text(encoding="utf-8"))
    src_plan_dir = Path(profile_path).parent

    # narrative 노드가 쓰는 값만 원본에서 시딩한다(정체성은 그래프가 건드리지 않는다).
    # style/music은 복사본을 넘겨 원본 객체를 변형하지 않는다(hook 노드가 style.hook을 갈아끼움).
    seed_run = make_run_id(src_profile.objective.goal)
    state = {
        "text_client": text_client,
        "image_client": None,  # 그래프는 이미지 작업을 하지 않는다.
        "tracer": Tracer(session_id=seed_run, run_id=seed_run),
        "objective": src_profile.objective,
        "product": src_profile.product,
        "meta": src_profile.meta,
        "character": src_profile.character,
        "environment": src_profile.asset_bible.environment,
        "style": src_profile.style.model_copy(deep=True),
        "music": src_profile.music.model_copy(deep=True),
        "delivery": src_profile.narration.delivery,
        "ref_voice_tone": src_profile.narration.voice.tone or "",
        "ref_voice_pace": src_profile.narration.voice.pace or "",
        "ref_hook": None,  # 새 아이디어: 레퍼런스 훅 오버레이를 끈다.
        "cut_count": len(src_profile.storyboard.panels),
        "hook_attempts": 0,
        "hook_feedback": "",
        "style_feedback": "",
    }
    final = build_replan_graph().invoke(state)

    # 새 훅 헤드라인으로 폴더를 명명한다(없으면 목적).
    new_hook = final["style"].hook
    keyword = (getattr(new_hook, "headline", None) or src_profile.objective.goal)
    new_run_id = make_run_id(keyword)
    new_plan_dir = create_run_dir(outputs_root, new_run_id) / "plan"
    new_plan_dir.mkdir(parents=True, exist_ok=True)

    # 정체성 에셋을 복사하고 asset_bible을 재사용(같은 상대 파일명 -> 새 폴더에서 해소).
    _copy_identity_assets(src_profile.asset_bible, src_plan_dir, new_plan_dir)
    asset_bible = src_profile.asset_bible.model_copy(deep=True)

    provenance = src_profile.provenance.model_copy(deep=True)
    provenance.seeds = {**provenance.seeds, "replanned_from": profile_path}

    new_profile = assemble_profile(
        {
            "objective": src_profile.objective,
            "product": src_profile.product,
            "meta": src_profile.meta,
            "character": src_profile.character,
            "style": final["style"],
            "narrative_arc": final.get("narrative_arc", []),
            "asset_bible": asset_bible,
            "storyboard": final["storyboard"],
            "narration": final["narration"],
            "music": final["music"],
            "provenance": provenance,
        }
    )

    # key_visual 재생성: 복사한 캐릭터·제품 참조로 새 커버를 그린다. 실패/부재 시 원본 복사 폴백.
    char_rel = asset_bible.character.key_shot_image
    prod_rel = asset_bible.product.hero_image
    char_ref = str(new_plan_dir / char_rel) if char_rel else None
    prod_ref = str(new_plan_dir / prod_rel) if prod_rel else None
    kv = build_key_visual(new_profile, image_client, str(new_plan_dir), char_ref, prod_ref)
    if kv:
        asset_bible.key_visual = kv
    elif src_profile.asset_bible.key_visual:  # 폴백: 원본 커버를 복사해 재사용
        old_kv = src_plan_dir / src_profile.asset_bible.key_visual
        if old_kv.exists():
            shutil.copy2(old_kv, new_plan_dir / src_profile.asset_bible.key_visual)
        asset_bible.key_visual = src_profile.asset_bible.key_visual

    return write_profile(new_profile, new_plan_dir, new_run_id)
```

Note on `_copy_identity_assets`: `CharacterProfile` has `key_shot_image`, `ProductProfile` has `hero_image`; both have `sheet_image` and `views`. Names are listed explicitly per type; `None` entries are skipped in the loop.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_run_replan.py -q`
Expected: PASS

- [ ] **Step 5: Typecheck, lint, commit**

Run: `.venv/bin/mypy src/reel_gen_agent/generate/planning_graph.py && .venv/bin/ruff check src/reel_gen_agent/generate/planning_graph.py tests/test_run_replan.py`
Expected: no errors

```bash
git add src/reel_gen_agent/generate/planning_graph.py tests/test_run_replan.py
git commit -m "feat(generate): add run_replan orchestrator (identity-locked re-approach)"
```

---

### Task 3: CLI `execute --replan` flag

**Files:**
- Modify: `src/reel_gen_agent/generate/../cli.py` (the `execute` command, around `cli.py:354-364`)
- Test: `tests/test_cli_replan.py`

**Interfaces:**
- Consumes: `run_replan` (Task 2); existing `make_text_client`, `_make_image_client`, `_produce` in `cli.py`.
- Produces: `execute` command gains `replan: bool = typer.Option(False, "--replan", ...)` and, when set, replans before producing.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_replan.py
"""execute --replan: run_replan로 새 프로필을 만든 뒤 그 프로필로 production을 돈다."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from reel_gen_agent import cli
from reel_gen_agent.generate.schema import RunManifest


def test_execute_replan_invokes_run_replan_then_produce(tmp_path, monkeypatch):
    original = tmp_path / "orig" / "plan" / "ReelProfile-orig.json"
    original.parent.mkdir(parents=True)
    original.write_text("{}", encoding="utf-8")

    new_profile = tmp_path / "new" / "plan" / "ReelProfile-new.json"
    new_profile.parent.mkdir(parents=True)
    new_profile.write_text("{}", encoding="utf-8")

    calls: dict = {}

    def fake_run_replan(profile_path, outputs_root, *, text_client, image_client):
        calls["replan_input"] = profile_path
        return new_profile

    def fake_produce(profile_path, *, use_vlm):
        calls["produced"] = profile_path
        return RunManifest(run_id="new", input_path=str(profile_path), final_video="out.mp4")

    monkeypatch.setattr(cli, "run_replan", fake_run_replan)
    monkeypatch.setattr(cli, "make_text_client", lambda: object())
    monkeypatch.setattr(cli, "_make_image_client", lambda: object())
    monkeypatch.setattr(cli, "_produce", fake_produce)

    result = CliRunner().invoke(cli.app, ["execute", str(original), "--replan"])

    assert result.exit_code == 0, result.output
    assert calls["replan_input"] == str(original)
    assert calls["produced"] == str(new_profile)


def test_execute_without_replan_produces_directly(tmp_path, monkeypatch):
    profile = tmp_path / "run" / "plan" / "ReelProfile.json"
    profile.parent.mkdir(parents=True)
    profile.write_text("{}", encoding="utf-8")

    seen: dict = {}

    def fake_produce(profile_path, *, use_vlm):
        seen["produced"] = profile_path
        return RunManifest(run_id="run", input_path=str(profile_path), final_video="out.mp4")

    monkeypatch.setattr(cli, "_produce", fake_produce)

    result = CliRunner().invoke(cli.app, ["execute", str(profile)])

    assert result.exit_code == 0, result.output
    assert seen["produced"] == str(profile)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_cli_replan.py -q`
Expected: FAIL — `test_execute_replan_invokes_run_replan_then_produce` errors on `--replan` (No such option) and/or `cli` has no attribute `run_replan`.

- [ ] **Step 3: Write minimal implementation**

Add the import near the other generate imports in `cli.py` (next to `from .generate.planning_graph import run_planning`):

```python
from .generate.planning_graph import run_planning, run_replan
```

Replace the `execute` command (`cli.py:354-364`) with:

```python
@app.command()
def execute(
    profile: str = typer.Argument(..., help="ReelProfile JSON 경로"),
    replan: bool = typer.Option(
        False,
        "--replan",
        help="정체성(제품·모델·에셋)은 고정하고 훅→스토리→나레이션→음악을 새 아이디어로 "
        "다시 뽑아 새 폴더의 ReelProfile로 생성한다.",
    ),
    outputs: str = typer.Option("outputs", help="출력 루트 디렉터리(--replan 시 새 폴더 위치)"),
    no_vlm: bool = typer.Option(False, "--no-vlm", help="rubric 채점을 건너뛴다."),
) -> None:
    """ReelProfile을 받아 Production을 돌려 outputs/<run_id>/에 영상·리포트를 만든다.

    --replan을 주면 먼저 같은 목적·같은 제품·같은 모델로 훅을 새로 잡아 스토리·나레이션·음악을
    다시 전개한 새 ReelProfile(새 폴더)을 만들고, 그걸로 production을 돌린다(다른 어프로치 1편).
    """
    if not Path(profile).exists():
        typer.echo(f"파일 없음: {profile}", err=True)
        raise typer.Exit(code=1)

    target = profile
    if replan:
        text = make_text_client()
        if text is None:
            typer.echo("--replan은 텍스트 LLM 키가 필요합니다(GEMINI_API_KEY 등).", err=True)
            raise typer.Exit(code=2)
        img = _make_image_client()  # key_visual 재생성용(없으면 원본 커버 폴백)
        new_path = _working(
            "재기획 중 (새 훅→스토리→나레이션→음악)",
            lambda: run_replan(profile, outputs, text_client=text, image_client=img),
        )
        typer.echo(f"재기획: 새 훅 -> 새 폴더 {new_path}", err=True)
        target = str(new_path)

    manifest = _working("영상 생성 중 (production)", lambda: _produce(target, use_vlm=not no_vlm))
    typer.echo(f"영상: {manifest.final_video}", err=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_cli_replan.py -q`
Expected: PASS (both tests)

- [ ] **Step 5: Typecheck, lint, commit**

Run: `.venv/bin/mypy src/reel_gen_agent/cli.py && .venv/bin/ruff check src/reel_gen_agent/cli.py tests/test_cli_replan.py`
Expected: no errors

```bash
git add src/reel_gen_agent/cli.py tests/test_cli_replan.py
git commit -m "feat(cli): add execute --replan flag"
```

---

### Task 4: Docs — document `--replan`

**Files:**
- Modify: `src/reel_gen_agent/cli.py:1-12` (module docstring command list)
- Modify: `docs/pipeline-design.md` (add a short "Replan" note; link `specs/replan.md`)
- Modify: `README.md` (add `execute --replan` to the usage/commands section if one exists)

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing (documentation only).

- [ ] **Step 1: Update the CLI module docstring**

In `cli.py`, change the `execute` line in the top docstring (`cli.py:9`) to:

```python
- execute: ReelProfile -> Production 실행 -> final.mp4 + upload.md + report.md. --replan 시 새 훅으로 재전개(새 폴더). 워킹 스켈레톤.
```

- [ ] **Step 2: Add a Replan note to docs/pipeline-design.md**

Append this section near the execute/stage description in `docs/pipeline-design.md` (match the file's existing heading style; verify the exact heading level by reading the file first):

```markdown
## Replan (execute --replan)

`execute --replan` re-approaches a frozen ReelProfile: it keeps the objective,
product, and model (identity assets are reused), re-rolls the narrative
(hook <-> storyboard, narration, music) from a fresh hook, regenerates the
key_visual, and writes a new `ReelProfile-<new-keyword>.json` into a new run
folder before producing it. See [specs/replan.md](../specs/replan.md).
```

- [ ] **Step 3: Add to README usage (if a command list exists)**

Read `README.md`; if it documents `execute`, add a sibling line/example:

```markdown
reel-gen execute <profile> --replan   # same goal, new hook/story/music -> new folder
```

If README has no command list, skip this step (do not invent a new section).

- [ ] **Step 4: Verify docs build/read cleanly and full suite passes**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: PASS, no lint errors

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/cli.py docs/pipeline-design.md README.md
git commit -m "docs: document execute --replan"
```

---

## Self-Review

**Spec coverage:**
- Sub-graph `replan_graph.py` reusing narrative nodes — Task 1. ✓
- `run_replan` orchestrator: seed from profile, new run id from new hook, copy identity assets, regenerate key_visual with fallback, provenance `replanned_from`, assemble+write — Task 2. ✓
- Identity locked (objective/product/character/meta + assets reused) — Task 2 (state seeding + asset copy) and asserted in test. ✓
- Narrative re-rolled, `ref_hook=None` — Task 2 state seeding. ✓
- key_visual regenerated with image-client-absent fallback — Task 2 + test. ✓
- New run folder — Task 2 + test. ✓
- No schema change — confirmed; no schema edits in any task. ✓
- CLI `--replan` (text client required, image optional, `--no-vlm` applies) — Task 3 + tests. ✓
- Done criteria "deterministic test covers new folder/copy/identity/narrative/key_visual fallback" — Task 2 test. ✓
- Docs — Task 4. ✓

**Placeholder scan:** No TBD/TODO; all code blocks are complete. README step is conditional but explicit about the condition. ✓

**Type consistency:** `run_replan(profile_path, outputs_root, *, text_client, image_client) -> Path` used identically in Task 2 (def), Task 3 (call + fake). `build_replan_graph()` defined Task 1, used Task 2. `build_key_visual` signature matches `asset_bible.py`. `_copy_identity_assets(bible, src_dir, dst_dir)` local to Task 2. ✓
