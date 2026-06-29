# Generation pipeline design

Status: designed, not yet implemented. This document is the contract a future
implementation follows. The analysis layer (`analyze`) is already built; the
generation stages below are not.

## Shape

```
generation_input.json
   ▼ [gate: concept]
asset bible (character + product images)
   ▼ [gate: asset_bible]   <- required
storyboard.json + panel stills
   ▼ [gate: storyboard]    <- approve before the expensive video step
video (image-to-video per panel + ffmpeg assembly)
   ▼ [gate: video]
Gate: profile(output) vs style_profile (similarity score)
```

Each step is a node followed by a confirm interrupt. The asset bible locks the
character and product look first, so every later step stays consistent. The
storyboard gate exists because the video step is the expensive one; you approve
the stills before spending on image-to-video.

## Human-in-the-loop gates

Every important step can confirm. A gate behaves in one of three ways:

- **ask** (default, chat mode): show the result, let the user confirm or edit.
- **pass** (`--force-step-pass <step>`, or `/pass <step>` inside the CLI): skip the
  prompt and continue.
- **run mode**: pass every gate, generate straight from the input.

This generalizes interactive review into a gate config, which is also the basis
for a non-interactive run mode (input in, video out, no prompts).

## Schemas

Defined in `src/reel_gen_agent/generate/schema.py`. The stable interface between
stages.

- `GenerationInput` — `meta` (duration, aspect_ratio, fps, platform, language),
  `product`, `model`, `style`, `voice`, `music`, `subtitle`, `narrative_arc`,
  `watermark`, `style_profile_ref`.
- `AssetBible` — `CharacterProfile` (sheet image + key shot) and `ProductProfile`
  (sheet image + hero shot). One multi-view sheet image per asset is enough,
  since the image model renders multiple views in a single image.
- `Storyboard` — a list of `StoryboardPanel`: `index`, `beat`, `t_start`, `t_end`,
  `shot_type`, `camera`, `subject_lock`, `product_lock`, `prompt`,
  `subtitle_text`, `cta_text`, `still_image`.

## Seeding the storyboard from the profile

Panel count and per-panel timing come from the analyzed cut data in
`style_profile.json` (`style_profile_ref` on the input). A reference with thirteen
fast cuts yields thirteen short panels; five slow cuts yields five long ones. The
edit rhythm is reproduced as a parameter, not a constant.

## Image and video backends

- **Images** (asset sheets and panel stills): Gemini image model
  (`GEMINI_IMAGE_MODEL`, default `gemini-3.1-flash-image`). Quality is the
  priority because still quality drives video quality. Panel stills pass the
  character and product reference images for consistency. A higher-tier image
  model is a later option.
- **Video**: per-panel image-to-video (`VEO_MODEL`), then ffmpeg concat, subtitle
  overlay (see below), background music mux (`LYRIA_MODEL` or provided), and
  watermark.
- **Low-cost fallback** (Stage C config): when the video model is off, render
  stills with Ken Burns motion through the same assembly path. The system runs
  end to end without a video-model budget.

## Subtitles and emoji

Emoji in captions (sparkle, heart, glow marks) are part of the hook in this
space, so color emoji must render correctly. Two common routes do not handle this
well:

- ffmpeg ASS burn via libass has poor color-emoji support (COLR/CBDT fonts render
  as monochrome glyphs or tofu).
- Plain Pillow has no automatic font fallback, so it draws latin/Korean text and
  emoji only if the string is manually split into text and emoji runs.

Approach: render each subtitle line to a transparent PNG with **pilmoji on top of
Pillow** (emoji composited from a bundled color set such as Noto Color Emoji or
Twemoji), then overlay the PNG onto the video at the panel's timing with ffmpeg.
This keeps color emoji intact, gives full control over font, outline, and
position, and adds no heavy system dependencies (unlike a pycairo/Pango stack,
which would add cairo and pango system libraries and install friction). pilmoji
handles the text/emoji run splitting that plain Pillow would require by hand.

Subtitle text and timing come from the storyboard panels, so no speech-to-text or
forced alignment is needed. pycairo/Pango stays a fallback only if complex text
shaping ever demands it.

## Module layout (to build)

```
src/reel_gen_agent/generate/
  schema.py        # present
  asset_bible.py   # image model -> character + product assets
  storyboard.py    # input + style_profile -> storyboard.json -> panel stills
  subtitles.py     # pilmoji -> transparent subtitle PNGs (color emoji preserved)
  video.py         # image-to-video per panel + ffmpeg assembly (subtitle overlay, Ken Burns fallback)
  gates.py         # GateConfig + confirm / edit / pass logic
  graph.py         # nodes + interrupt wiring
outputs/<run_id>/  # generation_input.json, assets/, storyboard/, panels/, final.mp4
```

## First implementation scope (walking skeleton)

Get one rough video end to end before polishing:

1. Start from a hand-authored `generation_input.json` (the concept LLM stage comes
   later).
2. asset bible -> [gate] -> storyboard JSON and stills -> [gate] -> image-to-video
   -> assembled mp4 -> [gate].
3. Include the gate framework (ask/pass, `--force-step-pass`, chat/run modes).

This produces a finished video while exercising the gates, asset bible, and
storyboard. The full concept and template stages come after.

## Voiceover (optional)

Off by default; the primary path is music bed plus subtitles. When enabled for a
demo, use emotion-tagged text-to-speech (for example `[curious] ... [cheerfully]
...`) so the delivery matches the beat.
