# Similarity loop: measure output-vs-reference and close the generation loop

Status: accepted (2026-07-01)

## Why

A reference drives style. The pipeline seeds a reference profile into a plan and
renders an output, but nothing measures whether the output actually *feels like*
the reference. Rubric (content effectiveness) and conformance (integrity) both
judge a clip on its own; neither answers "does this output match the reference's
visual language, cut rhythm, and audio character?"

Observed gaps (reference1 vs its reproduction, measured):

| axis | reference | output | drift |
|---|---|---|---|
| cut mean / mode | 1.19s / fast_montage | 1.78s / mixed | slower, rhythm lost |
| voice tone / pace | whispered soft / slow | enthusiastic / moderate | delivery mismatch |
| visual motion | gentle | dynamic | over-energetic |

Root causes (all in the reference -> plan -> render carry path):

- **R1 voice delivery dropped.** `reference_seed` ignores `voice.tone`/`voice.pace`;
  narration voice is derived only from the character persona.
- **R2 rhythm/energy hardcoded.** The storyboard principles hardcode "DYNAMIC and
  high-energy" and the Veo prompt hardcodes "fast-edited hard cuts", so a slow,
  gentle reference still renders fast and busy.
- **R3 SFX unwired.** `plan.sfx` / `Materials.sfx_audio` / cost exist, but no stage
  generates or mixes SFX; music is always a continuous bed.
- **R4 music prominence coarse.** BGM gain is a binary 0.6/0.28; a vocal/lyrical pop
  track that should be felt gets buried under narration ducking.

None of these are reference1-specific; the fix is to carry the measured profile
through, not to special-case any one video.

## What (this spec)

1. **Similarity measurement.** `analysis/similarity.py`:
   `compare_profiles(reference: VideoProfile, output: VideoProfile) -> SimilarityReport`.
   Per-axis normalized scores (0..1), weighted overall, pass/fail against a
   threshold, and per-axis human-readable deltas usable as plan feedback. Pure and
   deterministic; no model calls (operates on two already-computed profiles).

2. **`compare` CLI.** `reel-gen compare --reference <profile.json|video> --output <video>`
   re-analyzes as needed and prints a `SimilarityReport`. Non-zero exit on fail.

3. **Loop wiring.** `run` (and a new `refine`) re-analyze the final mp4, compare to
   the reference profile, and on fail feed the axis deltas back as `style_feedback`
   into a re-plan/re-execute, up to `--max-iters`.

## Similarity axes and weights

All read from `VideoProfile`. Weights sum to 1.0.

- **rhythm 0.28** — `cut.mode` (ordinal fast_montage/mixed/slow_demo) + `cut.mean_sec`
  ratio closeness.
- **voice 0.22** — `voice.present`/`on_camera` + `pace` (reliable base) with `tone`
  as a floored soft bonus (max +20%). (The "결" axis.)
- **music 0.15** — `dynamics` match + `bpm` closeness + `continuous` match.
- **visual 0.18** — `motion` ordinal + `brightness`/`contrast` closeness + palette
  soft overlap.
- **subtitle 0.09** — `density` + `position` match.
- **tone 0.05** — `tone` soft overlap.
- **narrative 0.03** — `narrative_arc` soft overlap.

These weights are the source of truth and mirror `analysis/similarity.py` (`_WEIGHTS`).
Deterministic axes (rhythm, voice base, music, visual, subtitle) carry more weight
than the free-text perceptual axes (tone, narrative), which stay low because judge
labels vary run to run.

Overall pass threshold: **0.78**. Each axis also has its own soft threshold (0.6)
below which it emits a delta line.

### Calibration against judge noise

The Gemini perceptual fields (`voice.tone`, `tone`, `narrative_arc`, `visual.motion`)
are free-text and vary run to run — analyzing the *same* video twice does not
reproduce identical labels. Measured self-noise: reference1 analyzed twice scores
only ~0.72 under exact-token matching, so a 0.78 gate is unreachable by
construction. The metric is calibrated so identical inputs land clearly above the
gate while genuinely weaker outputs stay below:

- **Soft matching** (`_soft_jaccard`): tokens match on a 4+ char shared prefix or
  substring (glow/glowy/glowing), so synonym-ish labels are not over-penalized.
- **Ordinal adjacency**: on 3+ level scales, adjacent labels (slow↔moderate) score
  0.7, not 0.5, because that gap is within judge noise. Two-level scales
  (flat/build) are not softened — there adjacent is the extreme.
- **Voice** leans on the reliable base (present/on_camera/pace); `tone` only adds a
  bonus so its instability cannot tank the axis.
- **tone/narrative** carry low weight — even a perfect reproduction cannot score
  them highly given judge variance.

Result: reference1 vs itself ≈ 0.84 (pass), the pre-fix reproduction ≈ 0.71 (fail).
The gate sits in that gap, so the loop converges instead of chasing label noise.

## Fidelity carriers (make the first pass honor the reference)

- **R1** `reference_seed` carries `voice.tone`/`voice.pace` into a `VoiceSpec`
  (`tone`, `pace`); narration blends persona + reference delivery; TTS description
  and line-writing honor it.
- **R2** derive an *edit-energy* directive from `style.pacing`/`cut.mode`
  (fast_montage -> snappy hard cuts + brisk moves; slow_demo -> long gentle holds +
  slow drifts). Thread it into the storyboard principles and the Veo prompt instead
  of the hardcoded strings.
- **R3** audio effects, split by who does them best:
  - **Diegetic in-scene sounds** (spray, tap, pour) are left to the video model
    (Veo/Kling audio), not synthesized separately.
  - **ElevenLabs SFX is optional and non-diegetic only** — produced edit effects
    (cut-transition whoosh, graphic/sparkle accents, hook riser, ending jingle) for
    a variety-show edit feel. The music node decides `sfx` (default off) and the
    storyboard emits sparse production-effect cues; when enabled, execute generates
    and mixes them. Music-off + SFX-only is supported. LLM/plan-driven, never
    hardcoded on.
- **R4** grade BGM prominence on a small scale and model whether the track is
  vocal/lyrical so a "felt" track is not over-ducked.

## Done criteria

- `compare` returns a `SimilarityReport` for any two profiles/videos.
- The reference1 reproduction's overall similarity rises above threshold, driven
  only by the carried profile (no reference1 constants in code or prompts).
- A different input (different product/reference) still produces a different result
  (the loop tunes toward its own reference, not a fixed target).
