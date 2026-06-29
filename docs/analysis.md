# Analysis layer

Turns a reference short-form video into a reusable `VideoProfile` (JSON). The same
`analyze_video(path)` function serves three callers:

- reference video to `style_profile.json` (Stage 0)
- downloaded URL to a reference catalog entry
- generated output to a profile for Gate similarity scoring

## Two layers, one profile

- **Deterministic (local, reproducible):** same input always yields the same
  numbers. The basis for Gate similarity.
  - `media_probe.py` (ffprobe): resolution, fps, duration, aspect ratio
  - `cut_detector.py` (PySceneDetect): cut count, mean/min/max cut length, mode
  - `audio_features.py` (librosa): BPM, build-vs-flat dynamics, intro silence
  - `visual_features.py` (OpenCV): dominant palette (hex), brightness, contrast
- **Perceptual (Gemini multimodal):** human-readable description plus category
  labels.
  - `gemini_describe.py`: voice tone, feel, subtitle style, hook, narrative arc

`analyze.py` merges both into one profile. Deterministic measurements are not
overwritten by the perceptual layer.

## Gemini input selection

Short videos upload whole through the File API so audio is analyzed too. If the
video stream is blocked by a content filter, or the video runs longer than sixty
seconds, the analyzer falls back to sampled keyframes (no audio). The fallback is
automatic, so analysis still completes.

## Run

```bash
reel-gen analyze video.mp4                         # JSON to stdout
reel-gen analyze video.mp4 --out profiles/x.json   # save + record source
reel-gen analyze video.mp4 --no-gemini             # deterministic only
```

## VideoProfile fields

`container`, `cut`, `visual`, `subtitle`, `voice`, `music`, `hook`, `tone`,
`narrative_arc`, `description`, `source`. The pydantic models in `profile.py` are
the source of truth.

## Notes

- The analyzer runs with `GEMINI_API_KEY` alone. Without it, the deterministic
  layer still produces a partial profile.
- Cut sensitivity is a parameter (PySceneDetect threshold). Lower it to catch
  faster dissolves. The point is that cut rhythm is data, not a constant.
