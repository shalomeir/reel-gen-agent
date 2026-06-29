# Architecture

`reel-gen-agent` keeps analysis and generation separate and connects them through
a stable JSON interface. The same engine that profiles a reference video also
scores a generated one, so both are judged on one ruler.

## Pipeline

```
reference.mp4
   │  analyze
   ▼
VideoProfile / style_profile.json        (Stage 0, implemented)
   │  seeds cut rhythm
   ▼
generation_input.json                    (Stage B output)
   ▼  [gate: concept]
asset bible (character + product images)  (designed)
   ▼  [gate: asset_bible]
storyboard.json + panel stills            (designed)
   ▼  [gate: storyboard]
video (image-to-video per panel + ffmpeg) (designed)
   ▼  [gate: video]
Gate: profile(output) vs style_profile    (similarity score)
```

## Why the split

The generation backend (image model, video model) is the part most likely to
change. Holding the schemas fixed means a backend swap touches one stage, not the
whole system. `style_profile.json` and the generation schemas are those fixed
interfaces.

## The closed loop

The analyzer measures cut count, cut lengths, and narrative arc from a reference.
The storyboard generator reads those numbers to decide how many panels to cut and
how long each runs. A reference with thirteen fast cuts produces a different
storyboard rhythm than one with five slow cuts, with no rule hardcoded. The
analyzer is the Stage 0 profiler, the storyboard seeder, and the Gate scorer.

## Modules

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
  generate/        # generation pipeline (designed; schema.py present)
    schema.py          # generation_input / asset bible / storyboard schemas
  cli.py           # typer CLI
```

See [analysis.md](analysis.md) for the analyzer and
[pipeline-design.md](pipeline-design.md) for the generation pipeline.
