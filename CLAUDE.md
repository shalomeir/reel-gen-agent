# CLAUDE.md

Working guide for humans and coding agents (Claude Code and others) in this
repository. `AGENTS.md` is a symlink to this file, so both names resolve to the
same content. Read this before making changes. The product intent and success
criteria live in [specs/project-brief.md](specs/project-brief.md).

## What this project is

reel-gen-agent is an open-source CLI that generates a one-person, product-focused
vertical short for Instagram Reels, TikTok, and YouTube Shorts. A user supplies a
product and a reference style; the agent returns a post-ready mp4 with a model,
captions, and music. It targets solo creators and small brands doing short-form
promotion and brand awareness.

Product fit: anything a single person can show worn or used on camera in an indoor
room. The default model, styling, palette, and voice lean feminine, since that is
where short-form product PPL concentrates. Skincare is the top category (serums,
sunscreen, toner and moisturizer, cleansers, patches), followed by makeup (cushion
and foundation, lip, eyeshadow). It also covers adjacent beauty and wellness
(supplements and diet, clinic treatments, innerwear and athleisure) and extends to
apparel, accessories, bags, shoes, eyewear, and simple home decor props. Keep this
feminine-leaning default in generation defaults (model, palette, voice, tone).

The guiding principle: do not hardcode a style. Measure it from a reference,
express it as reusable data, and drive generation from that data. The same engine
that profiles a reference also scores a generated clip, so references and outputs
are judged on one ruler.

Analysis is built; the generation pipeline is designed and being implemented stage
by stage.

## Repository layout

```
src/reel_gen_agent/
  analysis/        # reference video -> VideoProfile (implemented)
    profile.py         # VideoProfile schema (pydantic)
    media_probe.py     # ffprobe: container metadata
    cut_detector.py    # PySceneDetect: cut distribution
    audio_features.py  # librosa: audio dynamics
    visual_features.py # OpenCV: palette, brightness
    frame_sampler.py   # uniform frame sampling: black/freeze/flicker metrics
    loudness.py        # BS.1770 integrated loudness (LUFS) + peak
    gemini_client.py   # shared Gemini multimodal plumbing (upload/frame fallback)
    gemini_describe.py # Gemini: perceptual fields
    rubric.py          # driver rubric: VideoProfile + video -> RubricResult (soft gate)
    list_writer.py     # profile -> reference catalog entry
    analyze.py         # orchestrator: analyze_video(path)
  generate/        # generation pipeline (schema present; stages designed)
    schema.py          # generation_input / asset bible / storyboard / RunManifest schemas
    conformance.py     # conformance gate: video + template/manifest -> ConformanceReport (hard pass/fail)
  cli.py           # typer CLI (analyze[url|path], add-reference, evaluate, verify, plan, execute, run, chat)
specs/             # planning docs: project-brief.md, rubric.md, conformance-gate.md, …
docs/              # architecture and usage docs (incl. rubric.md rationale)
tests/             # pytest
utils/             # add-reference.sh and helper scripts
outputs/           # generated runs (gitignored)
profiles/          # analysis output JSON (gitignored)
evals/             # rubric + conformance output JSON (gitignored)
```

## The architecture invariant

Analysis and generation communicate only through the pydantic schemas
(`src/reel_gen_agent/analysis/profile.py`, `src/reel_gen_agent/generate/schema.py`).
The image and video backends are the parts most likely to change; holding the
schemas fixed means a backend swap touches one stage, not the system. If a change
blurs that boundary or couples a generation stage to analysis internals,
reconsider it.

Two-layer analysis: a deterministic local layer (ffprobe, PySceneDetect, librosa,
OpenCV) produces reproducible numbers; a Gemini layer adds perceptual description.
Deterministic measurements are never overwritten by the perceptual layer.

## How development is managed

This codebase evolves through small, documented iterations rather than big
rewrites. The loop:

1. **Spec first.** Non-trivial work starts as a document in `specs/`. The baseline
   is `specs/project-brief.md`; each feature or stage gets its own
   `specs/<topic>.md` describing intent, interface, and done-criteria before code.
2. **Brainstorm before building.** For anything new, agree on the design (the
   interface, the trade-offs, the scope) before writing implementation. Capture
   the agreed design in `specs/`.
3. **Walking skeleton over polish.** Prefer a thin slice that runs end to end
   (rough but complete) before deepening any single stage. A finished-but-ugly
   clip beats a perfect half-pipeline.
4. **One change, one focus.** Keep changes scoped to a single stage or concern so
   they stay reviewable and the schemas stay clean.

## Stages and gates

The generation pipeline is a sequence of stages, each behind its schema and a
human-in-the-loop gate. A gate behaves as **ask** (confirm/edit), **pass**
(`--force-step-pass <step>`), or **run mode** (all gates pass). When adding a
stage, wire its gate the same way so chat mode and run mode stay consistent. The
stage plan and intended first slice (walking skeleton) are in
[docs/pipeline-design.md](docs/pipeline-design.md).

When adding a stage:
1. Define or reuse its schema in `generate/schema.py`.
2. Implement the stage as a focused module with a single entry function.
3. Wire its gate (ask / pass / run) into the graph.
4. Write a deterministic test; mock external model calls.

## Source of truth: specs over docs

`specs/` is the only authority for what gets built. `docs/` is a reference
library, not a contract.

- **`specs/` is binding.** Implementation follows what `specs/` defines and
  nothing else. If code and a `specs/` file disagree, the spec wins (or the spec
  is wrong and gets fixed first). `specs/project-brief.md` is the root vision,
  `specs/prd.md` is the product requirements, `specs/product-design.md` is the
  CLI/UX contract (chatbot CLI, chat/run modes and gates, input forms, and the
  `execute` direct-render command), and `specs/trd.md` is the technical contract
  (stack, libraries, external service clients, system layering, and constraints).
  Every coding step must follow these. Each further feature or stage gets its own
  dated `specs/<topic>.md` describing intent, interface, and done-criteria before
  code.
- **`docs/` is reference material only.** Architecture notes, analysis write-ups,
  pipeline explorations, and usage guides live here as background and rationale.
  They inform decisions but do not by themselves authorize implementation. When a
  `docs/` design is accepted as the plan, promote the binding parts into a
  `specs/` file and let `docs/` keep the longer explanation.
- When `specs/` and `docs/` conflict, resolve it in `specs/`. Do not duplicate
  content across the two; link instead.

## Conventions and code quality

- Python 3.10+, four-space indent, PEP 8 (`snake_case` functions and variables,
  `PascalCase` classes, `UPPER_SNAKE_CASE` constants). Filenames are `kebab-case`
  for scripts and docs, `snake_case` for Python modules.
- Comments explain the "why", not the "what". Public functions get docstrings.
- Each module has one clear responsibility and communicates through the schemas.
  When a file grows past its one job, split it.
- End files with a trailing newline. UTF-8 throughout.
- Typecheck and run `pytest -q` after a series of changes. Prefer running the
  specific test over the whole suite while iterating.
- Tests are independent and generate their own data. Mock external model calls;
  keep the deterministic layer covered by real assertions.

## Running and testing

This project uses `uv` and a project-local `.venv`. Always run inside that
`.venv`; never install or run against the global / pyenv Python. The repo ships an
`.envrc` that activates `.venv` and loads `.env` via direnv, so an interactive
shell in this directory is already set up.

Caveat for coding agents: a non-interactive shell (the kind tool calls run in)
does not trigger the direnv hook, so `.venv` is not auto-activated and commands
fall back to the global Python. Activate it explicitly first, or call the venv
binaries directly:

```bash
source .venv/bin/activate        # then run reel-gen / pytest / ruff directly
# or, per command, without activating:
uv run reel-gen --help           # uv run wraps the .venv
.venv/bin/reel-gen --help        # call the venv binary directly
```

Setup and the usual loop, all inside `.venv`:

```bash
uv sync --extra dev              # create .venv + install package and dev deps
cp .env.example .env             # then fill GEMINI_API_KEY

reel-gen analyze video.mp4               # analyze a reference
reel-gen analyze video.mp4 --no-gemini   # deterministic only, no key needed

pytest -q                        # run tests (video tests skip if no sample)
ruff check src tests             # lint
ruff format src tests            # format
mypy                             # type check
```

Add a reference video for local testing (downloads to `reference_video/`, which
the deterministic tests pick up automatically):

```bash
utils/add-reference.sh "https://www.youtube.com/shorts/..."
```

## Reference curation

References drive the style. Keep a short note of why each reference was added
(what axis of variation it covers), not just the file. This keeps the reference
set intentional rather than a random pile.

## Version control

- Branches: `main` is the stable baseline, `develop` is integration, `feature/*`
  for new work, `bugfix/*` for fixes.
- Commit messages: `type(scope): subject` (`feat`, `fix`, `docs`, `refactor`,
  `test`, `chore`), imperative subject under ~50 chars, body for the "why".
- Do not commit secrets, large media, or generated output (see `.gitignore`).

## Security and keys

- A single required key, `GEMINI_API_KEY`, covers analysis and image generation.
  Other model keys are optional and added only when a stage needs them.
- Keys live in `.env` (gitignored). `.env.example` lists names, sources, and
  purposes with no values, so anyone can inject their own key and run.

## Do not

- Hardcode style constants that should be parameters.
- Commit secrets. Keys live in `.env`; `.env.example` lists names only.
- Commit large media or generated output. `outputs/`, `profiles/*.json`, and
  `*.mp4` are gitignored.
