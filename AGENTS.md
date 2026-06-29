# AGENTS.md

Guidance for humans and AI agents working in this repository. Read this before
making changes.

## What this project is

reel-gen-agent is an open-source CLI that generates a one-person, product-focused
vertical short for Instagram Reels, TikTok, and YouTube Shorts. A user supplies a
product and a reference style; the agent returns a post-ready mp4 with a model,
captions, and music. Beauty and skincare channels are the primary target vertical.

The guiding principle: do not hardcode a style. Measure it from a reference,
express it as reusable data, and drive generation from that data. The full intent
and success criteria live in [specs/project-brief.md](specs/project-brief.md).

## Repository layout

```
src/reel_gen_agent/
  analysis/        # reference video -> VideoProfile (implemented)
    profile.py         # VideoProfile schema (pydantic)
    media_probe.py     # ffprobe: container metadata
    cut_detector.py    # PySceneDetect: cut distribution
    audio_features.py  # librosa: audio dynamics
    visual_features.py # OpenCV: palette, brightness
    gemini_describe.py # Gemini: perceptual fields
    list_writer.py     # profile -> reference catalog entry
    analyze.py         # orchestrator: analyze_video(path)
  generate/        # generation pipeline (schema present; stages designed)
    schema.py          # generation_input / asset bible / storyboard schemas
  cli.py           # typer CLI (analyze works, generate is a stub)
specs/             # planning docs: project-brief.md and future feature specs
docs/              # architecture and usage docs
tests/             # pytest
utils/             # add-reference.sh and helper scripts
outputs/           # generated runs (gitignored)
profiles/          # analysis output JSON (gitignored)
```

## The architecture invariant

Analysis and generation stay separate, connected only through the pydantic schemas
(`analysis/profile.py`, `generate/schema.py`). A change to an image or video
backend must not require touching the analysis layer or the schemas. If a change
blurs that boundary, reconsider it.

Two-layer analysis: a deterministic local layer (ffprobe, PySceneDetect, librosa,
OpenCV) produces reproducible numbers; a Gemini layer adds perceptual description.
Deterministic measurements are never overwritten by the perceptual layer.

## Conventions

- Python 3.10+, four-space indent.
- Naming: `camelCase` is not used in Python here; follow PEP 8 (`snake_case`
  functions and variables, `PascalCase` classes, `UPPER_SNAKE_CASE` constants).
  Filenames are `kebab-case` for scripts and docs, `snake_case` for Python modules.
- Comments explain the "why", not the "what". Public functions get docstrings.
- Each module has one clear responsibility and communicates through the schemas.
  When a file grows past its one job, split it.
- End files with a trailing newline. UTF-8 throughout.

## Running and testing

```bash
pip install -e ".[dev]"          # editable install + dev deps
cp .env.example .env             # then fill GEMINI_API_KEY

reel-gen analyze video.mp4               # analyze a reference
reel-gen analyze video.mp4 --no-gemini   # deterministic only, no key needed

pytest -q                        # run tests (video tests skip if no sample)
```

Add a reference video for local testing:

```bash
utils/add-reference.sh "https://www.youtube.com/shorts/..."   # downloads to reference_video/
```

When testing the analyzer, drop any mp4 under `reference_video/` and the
deterministic tests will pick it up.

## Extending the pipeline

The generation stages are designed but not built. Implement them in dependency
order, each behind its schema and gate. The intended first slice (walking
skeleton) and module plan are in [docs/pipeline-design.md](docs/pipeline-design.md).

When adding a stage:
1. Define or reuse its schema in `generate/schema.py`.
2. Implement the stage as a focused module with a single entry function.
3. Wire its gate (ask / pass / run) into the graph.
4. Write a deterministic test; mock external model calls.

## Reference curation

References drive the style. Keep a short note of why each reference was added
(what axis of variation it covers), not just the file. This keeps the reference
set intentional rather than a random pile.

## Do not

- Hardcode style constants that should be parameters.
- Commit secrets. Keys live in `.env` (gitignored); `.env.example` lists names
  only.
- Commit large media or generated output. `outputs/`, `profiles/*.json`, and
  `*.mp4` are gitignored.
