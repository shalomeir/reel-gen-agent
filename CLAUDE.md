# CLAUDE.md

Working guide for Claude Code (and other coding agents) in this repository. The
shared project description, layout, and conventions live in
[AGENTS.md](AGENTS.md) and [specs/project-brief.md](specs/project-brief.md). Read
those first. This file adds how the codebase is meant to grow over many
iterations.

## What we are building

An open-source CLI that generates a one-person, product-focused vertical short for
Instagram Reels, TikTok, and YouTube Shorts, aimed at solo creators and small
brands, beauty channels first. Analysis is built; the generation pipeline is
designed and being implemented stage by stage.

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

## The invariant to protect

Analysis and generation communicate only through the pydantic schemas
(`src/reel_gen_agent/analysis/profile.py`, `src/reel_gen_agent/generate/schema.py`).
The image and video backends are the parts most likely to change; holding the
schemas fixed means a backend swap touches one stage, not the system. Do not let a
convenience shortcut couple a generation stage to analysis internals.

## Stages and gates

The generation pipeline is a sequence of stages, each behind its schema and a
human-in-the-loop gate. A gate behaves as **ask** (confirm/edit), **pass**
(`--force-step-pass <step>`), or **run mode** (all gates pass). When adding a
stage, wire its gate the same way so chat mode and run mode stay consistent. The
stage plan is in [docs/pipeline-design.md](docs/pipeline-design.md).

## Specs folder discipline

- `specs/project-brief.md` is the root. Keep it current when scope shifts.
- New design work lands as a new `specs/` file, dated in the body, referenced from
  the brief or the relevant doc.
- `docs/` holds stable architecture and usage docs; `specs/` holds the planning
  and design trail. Do not duplicate; link.

## Code quality

- Follow the conventions in AGENTS.md (PEP 8, docstrings on public functions,
  comments explain "why", one responsibility per module, trailing newline, UTF-8).
- Typecheck and run `pytest -q` after a series of changes. Prefer running the
  specific test over the whole suite while iterating.
- Tests are independent and generate their own data. Mock external model calls;
  keep the deterministic layer covered by real assertions.

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
