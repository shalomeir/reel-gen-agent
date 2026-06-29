# Project brief

The source-of-truth document for what reel-gen-agent is, why it exists, and what
"done" looks like. Other docs in `specs/` build on this one.

## Purpose

Let one person produce a polished, product-focused vertical short for Instagram
Reels, TikTok, or YouTube Shorts without a video team. The user supplies a product
and a reference style; the agent returns a post-ready mp4 with a model, on-screen
captions, and music.

Primary audience: solo short-form creators and small DTC brands running product
promotion and brand-awareness clips. Beauty and skincare channels are the main
target vertical, since that space leans on a recognizable short-form grammar
(hook, problem, application, payoff, glow). The tool is not limited to beauty, but
the defaults and references assume it.

Distribution: an open-source CLI. Anyone with an API key can run it for the cost of
their own model usage. No hosted service, no account, no lock-in.

## Core development content

1. **Analysis (built).** Turn a reference short into a reusable `VideoProfile`
   (JSON). A deterministic layer measures cut rhythm, audio dynamics, and color;
   a Gemini layer reads tone, voice, subtitle style, hook, and narrative arc.
2. **Generation pipeline (designed).** From a `generation_input.json`:
   - an **asset bible** (consistent character and product reference images),
   - a **storyboard** (panels with per-panel timing seeded from the analyzed cut
     rhythm),
   - a **video** assembled from per-panel image-to-video plus ffmpeg (subtitles,
     music, watermark).
3. **Human-in-the-loop gates.** Each important step can confirm and edit; a
   `--force-step-pass` flag skips chosen steps; a run mode passes everything for
   one-shot generation.
4. **Gate scoring.** The analyzer re-profiles the generated clip and scores it
   against the target style profile, closing the loop.

The architecture keeps analysis and generation separate behind pydantic schemas
so the image or video backend can be swapped without rewriting the pipeline. See
[../docs/architecture.md](../docs/architecture.md) and
[../docs/pipeline-design.md](../docs/pipeline-design.md).

## Constraints

- **Local-first CLI.** Runs on a laptop. No web frontend, no serverless deploy
  (an ffmpeg video pipeline does not fit serverless limits). The core is a
  package the CLI calls in-process, so a future web layer could wrap the same
  core.
- **Bring your own keys.** A single required key (`GEMINI_API_KEY`) covers
  analysis and image generation. Video and music models are optional and add
  keys only when used.
- **Cost-aware.** Image and analysis default to flash-tier models. The video step
  has a stills-plus-motion fallback so the pipeline runs end to end without a
  video-model budget.
- **No talking-head lip-sync.** The primary output is music bed plus subtitles.
  Voiceover is an optional, off-by-default demo path.
- **Vertical 9:16, roughly 10 to 60 seconds.** The format short-form platforms
  expect.

## Expected final deliverable

- A `reel-gen` CLI with two main commands:
  - `analyze <video>` — reference to `VideoProfile` JSON. (built)
  - `generate <input.json>` — input to finished mp4 through the gated pipeline.
- Reproducible runs under `outputs/<run_id>/` holding the input, asset bible,
  storyboard, panel stills, and `final.mp4`.
- The same input run through different reference styles yields visibly different
  results, demonstrating that style is data, not hardcoded.
- Documentation that lets a new contributor install, set a key, and produce a
  short.

## Success use cases

1. **Solo beauty creator, one product.**
   Input: a serum, its one-line benefit, and a reference reel with a fast-cut UGC
   feel. Approve the model and product art, approve the storyboard, get a 15s
   vertical clip with keyword captions and an upbeat bed. Post it the same day.

2. **Small brand, three variations.**
   Same product, three different reference styles (fast UGC, slow clinical demo,
   cinematic brand film). The agent produces three distinct edits from one input,
   so the brand can A/B which rhythm performs.

3. **Match a reference's rhythm for a new product.**
   Analyze a reel that performed well, then generate a new clip for a different
   product that reproduces its cut count and pacing. The storyboard panel count
   and timing come straight from the analyzed profile.

4. **One-shot run mode.**
   A user who trusts the defaults runs generation with all gates passed and gets a
   finished mp4 from a single input file, no prompts. The interactive gates exist
   for when they want control, not as a requirement.

## Out of scope (for now)

- Hosted SaaS, accounts, billing.
- Lip-synced talking avatars.
- Non-vertical or long-form formats.
- A GUI. The CLI is the product surface; a web layer can wrap the core later.
