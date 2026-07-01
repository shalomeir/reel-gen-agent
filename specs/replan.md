# Replan: re-approach a frozen ReelProfile with a fresh hook

Status: accepted (2026-07-01)

## Why

`plan` freezes one interpretation of a brief into a `ReelProfile` (hook, story,
narration, music, and the identity assets: character, product, environment,
key visual). Getting a *different creative approach* to the same goal today means
re-running `plan` from scratch, which re-derives the character and product and
regenerates every image asset. That is slow, costs image generations, and drifts
the model's face and the product look between takes, so the two videos are not
comparable "same product, different idea" siblings.

What a creator actually wants after seeing take one is: *keep the same objective,
the same product, and the same model, but start the hook over from a new idea and
let the story, narration, and music follow that new hook.* That is a cheap,
text-driven re-roll of the narrative on top of frozen identity assets, not a full
replan.

## What (this spec)

Add a first-level `rerun` command. It reads an existing `ReelProfile`, regenerates
only the narrative (style, hook <-> storyboard ping-pong, narration, music) from a
fresh hook, reuses the frozen identity assets, writes a new
`ReelProfile-<new-keyword>.json` into a new run folder, and then runs production on
it. The result is a second video for the same goal, coexisting with the original.
(This replaces the earlier `execute --replan` flag: re-rolling a narrative is a
distinct operation from rendering a profile as-is, so it gets its own verb.)

Scope decisions (confirmed):

- **Identity is locked.** `objective`, `product`, `character` (ModelSpec), and
  `meta` are carried over verbatim. The character/product/environment image assets
  are reused (copied), not regenerated. This keeps the model's face and the product
  consistent across takes and keeps replan cheap.
- **Narrative is re-rolled, style first.** style, hook, storyboard, narration,
  music, and the derived `narrative_arc` / `style.hook` are produced anew. rerun
  ignores the reference and regenerates style from scratch (state carries no
  `provenance`, so the style node takes the no-reference LLM path), then style leads
  the hook/story and is refined again after the ping-pong. The hook is a genuinely
  new idea: the reference-hook overlay is disabled (`ref_hook=None`) so the LLM is
  not re-pinned to the reference's headline. Regenerating style is what makes rerun
  actually diverge instead of reproducing the previous take.
- **key_visual is regenerated.** The representative cover is rebuilt from the
  reused character/product refs to match the new hook. If no image client is
  available, replan falls back to reusing the original key_visual instead of hard
  failing.
- **New run folder.** Output goes to `outputs/<new_run_id>/`, so the new take does
  not clobber the original's `final.mp4` / `report.md`.
- **No schema change.** Replan is a pure re-composition inside the generation side.
  The analysis <-> generation invariant (they communicate only through the pydantic
  schemas) is untouched.

## Interface

### Sub-graph: `generate/replan_graph.py`

A focused LangGraph that reuses the existing plan nodes for the narrative segment
only:

```
START -> hook -> storyboard -(_route_after_storyboard)-> [hook | narration]
      -> narration -> music -> END
```

It imports and reuses `_hook_node`, `_storyboard_node`, `_route_after_storyboard`,
`_narration_node`, and `_music_node` from `plan_graph.py` unchanged. None of these
nodes touch the image client or the plan asset directory, so the sub-graph is
text-only. There is no `write_profile` node; assembly and paths are handled by the
orchestrator (the new keyword is unknown until the hook is regenerated).

`build_replan_graph()` compiles and returns the graph.

### Orchestrator: `run_replan(...)` in `generate/planning_graph.py`

```python
def run_replan(
    profile_path: str,
    outputs_root: str,
    *,
    text_client: TextClient | None = None,
    image_client: ImageClient | None = None,
) -> Path:
```

Steps:

1. Load `ReelProfile` from `profile_path`; resolve the original `plan_dir`
   (`Path(profile_path).parent`).
2. Seed `PlanState` from the profile:
   - `objective`, `product`, `meta`, `character` (ModelSpec), `style`,
     `music` (seed prefs), `environment` (`profile.asset_bible.environment`).
   - `raw = profile.objective.goal` (hook node uses it as the brief).
   - `delivery = profile.narration.delivery`; `ref_voice_tone` / `ref_voice_pace`
     from `profile.narration.voice` so the voice character carries over.
   - `cut_count = len(profile.storyboard.panels)` to hold duration/timing.
   - `ref_hook = None`, `ref_subject = None`, `ref_product = None`,
     `hook_attempts = 0`, `hook_feedback = ""`, `style_feedback = ""`.
   - `image_client = None` inside the graph (no image work in the sub-graph).
   - a `Tracer` (session/run id from a provisional id; final run id is set later).
3. Invoke the sub-graph -> new `storyboard`, `narration`, `music`,
   `style` (with new `style.hook`), `narrative_arc`.
4. Derive the new keyword from `style.hook.headline` (fallback: objective goal) and
   `new_run_id = make_run_id(keyword)`. Create `outputs/<new_run_id>/plan/`.
5. Copy the frozen identity asset image files from the original `plan_dir` into the
   new plan dir: character `sheet_image` / `key_shot_image` / `views[].image`,
   product `sheet_image` / `hero_image` / `views[].image`,
   `environment.reference_image`. Missing files are skipped. key_visual is *not*
   copied (it is regenerated).
6. Rebuild `AssetBible` reusing the copied character/product/environment
   (`profile.asset_bible`), then regenerate `key_visual` with
   `build_key_visual(new_profile, image_client, new_plan_dir, char_ref, prod_ref)`.
   If `image_client is None` or regeneration fails, copy and reuse the original
   `key_visual` instead.
7. Mark provenance: `provenance.seeds["replanned_from"] = profile_path`.
8. `assemble_profile(...)` with the reused identity parts + new narrative, then
   `write_profile(...)` into the new plan dir. Return the new profile path.

### CLI: `rerun`

```
reel-gen rerun <profile>
```

- `rerun` is a first-level command (not a flag on `execute`). It builds
  `text_client` (required; refuse with a clear message if no text LLM key) and
  `image_client` (optional, for key_visual), calls `run_replan`, prints
  `재기획: 새 폴더 <path>`, then `_produce(new_profile, ...)` on the new profile.
  `--no-vlm` still applies to the production step.
- `execute <profile>` stays as-is: render the given profile directly, no re-roll.

## Done criteria

- `reel-gen rerun <profile>` produces a new `outputs/<run>/final.mp4`
  in a new folder, leaving the original run untouched.
- The new `ReelProfile` shares `objective`, `product`, and `character` with the
  original but has a different `storyboard`, `narration`, `music`, and
  `style.hook`.
- Identity asset image files exist in the new plan dir (copied), and key_visual is
  present (regenerated, or reused on image-client fallback).
- Deterministic test (mocked text/image clients) covers: new folder created,
  identity assets copied, identity fields unchanged, narrative fields regenerated,
  and the image-client-absent key_visual fallback.
- `pytest -q`, `ruff check`, and `mypy` pass.

## Non-goals

- Re-deriving the character or product (identity is locked).
- Any schema change or new external backend.
- Iterating replan in a loop or scoring the re-approach against the original;
  replan produces one alternative take. (Similarity scoring stays in `run`.)
