# reel-gen-agent

An AI agent CLI that turns a single product into a ready-to-post vertical short
for Instagram Reels, TikTok, and YouTube Shorts. Point it at a product, pick a
reference style, and it produces a one-person short-form clip with a model,
subtitles, and music. It is built for solo creators and small brands doing
short-form promotion and brand awareness, with beauty channels as the primary
use case.

Bring your own API key and start making shorts for free. No timeline editor, no
render farm: describe the product, approve a few steps, get an mp4.

Under the hood it separates **analysis** from **generation** through a stable JSON
interface, so the generation backend can change without touching the rest. The
core idea: do not hardcode a style. Measure it from references, express it as
reusable data, and drive generation from that data. The same engine that profiles
a reference also scores a generated clip, so references and outputs are judged on
one ruler.

## Status

- `analyze` — implemented. Reference video to a structured `VideoProfile` (JSON).
- `generate` — designed, not yet implemented. See [docs/pipeline-design.md](docs/pipeline-design.md).

## How it works

Two layers feed one profile:

- **Deterministic layer** (local, reproducible): cut distribution, audio dynamics,
  color and brightness. The numeric basis for similarity scoring.
  - `ffprobe` for container metadata
  - PySceneDetect for cut count, length distribution, edit mode
  - librosa for BPM, build-vs-flat dynamics, intro silence
  - OpenCV for dominant palette, brightness, contrast
- **Perceptual layer** (Gemini multimodal): voice tone, overall feel, subtitle
  style, hook, narrative arc.

The generation pipeline (designed) turns a `generation_input.json` into an asset
bible (character and product reference images), a storyboard JSON with per-panel
timing seeded from the analyzed cut rhythm, and finally an assembled video via
image-to-video plus ffmpeg. Every important step is gated for human confirm and
edit, with a non-interactive run mode that passes all gates. Details in
[docs/pipeline-design.md](docs/pipeline-design.md).

## Install

Requires Python 3.10+ and `ffmpeg`/`ffprobe` on PATH.

```bash
brew install ffmpeg            # macOS
pip install -e .               # installs the `reel-gen` command
# or: pip install -r requirements.txt
```

## Environment setup

Copy `.env.example` to `.env` and fill in your own keys.

```bash
cp .env.example .env
```

| Variable | Required | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | yes | Multimodal analysis + image generation. Get one at [Google AI Studio](https://aistudio.google.com/apikey). |
| `GEMINI_ANALYSIS_MODEL` | no | Analysis model. Default `gemini-2.5-flash`. |
| `GEMINI_IMAGE_MODEL` | no | Image model. Default `gemini-3.1-flash-image`. |
| `VEO_MODEL` | no | Image-to-video model (generation stage). |
| `LYRIA_MODEL` | no | Background music model (generation stage). |
| `ELEVENLABS_API_KEY` | no | Optional voiceover demo. |

The analyzer runs with `GEMINI_API_KEY` alone. Without it, the deterministic layer
still produces a partial profile and the perceptual fields stay empty.

## Run

```bash
# Analyze a reference video, print JSON to stdout
reel-gen analyze path/to/video.mp4

# Save to a file and record the source URL
reel-gen analyze path/to/video.mp4 --url "https://..." --out profiles/sample.json

# Deterministic layer only (no API key needed)
reel-gen analyze path/to/video.mp4 --no-gemini
```

A helper script downloads a reference from YouTube/TikTok into `reference_video/`:

```bash
utils/add-reference.sh "https://www.youtube.com/shorts/..."
```

## Test

```bash
pip install -e ".[dev]"
pytest -q
```

## Tooling choices

- **Gemini** for the perceptual layer and image generation: one multimodal model
  reads tone, voice, subtitle style, and hook, then renders consistent reference
  art. One key covers analysis and image generation.
- **PySceneDetect / librosa / OpenCV / ffmpeg** for the deterministic layer:
  measured numbers that are reproducible and cheap, which the Gate can compare.
- **pydantic** for the schemas that connect stages, so the generation backend can
  be swapped without breaking consumers.
- **typer + rich** for an in-process CLI with human-in-the-loop confirm gates.

## License

MIT. See [LICENSE](LICENSE).
