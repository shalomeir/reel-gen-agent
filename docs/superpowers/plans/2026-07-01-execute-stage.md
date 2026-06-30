# Execute Stage (Production) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `execute` stage that takes a frozen `ReelProfile` and produces a post-ready mp4 plus `report.md` and `upload.md`, running production planning, material generation, assembly, the verify→repair loop, describe, evaluate, and report.

**Architecture:** A LangGraph production graph whose nodes communicate through the pydantic schemas in `generate/schema.py`. Backends (video renderer, image, voice, music) sit behind small adapter interfaces so a backend swap touches one module. The walking skeleton uses the deterministic Ken Burns renderer (no external model) so the whole pipeline runs end to end with zero API keys; real video/voice/music backends are added behind the same interfaces afterward.

**Tech Stack:** Python 3.10+, pydantic v2, LangGraph, ffmpeg (system) + moviepy, pillow + pilmoji, tenacity. Tests with pytest; external model calls mocked.

## Global Constraints

- Python 3.10+, four-space indent, PEP 8. `snake_case` functions/vars, `PascalCase` classes, `UPPER_SNAKE_CASE` constants. Modules `snake_case`, docs/scripts `kebab-case`. UTF-8, trailing newline.
- Run everything inside the worktree-local `.venv` (`uv sync --extra dev` first). Never the global/pyenv Python. Use `uv run <cmd>` or the venv binaries.
- Schemas are the only boundary. execute consumes `ReelProfile`, produces `RunManifest` + artifacts. Never import plan-stage internals; communicate only through `generate/schema.py`. ([ADR.md](../../../specs/ADR.md) ADR-0003)
- Model-agnostic: model IDs and `GENAI_BACKEND` come from `.env`, never hardcoded. ([ADR.md] ADR-0008)
- Video format guardrails are enforced by `InputMeta` validators (9:16, ≤1080x1920, 1–60s, fps {24,25,30,50,60}, mp4/H.264/AAC). Assembly encodes to these. Source of truth: [trd.md](../../../specs/trd.md).
- Output folder is the directory **containing the given ReelProfile** (`outputs/<run_id>/`); execute writes into it. It does not create or name the folder — plan-stage owns `run_id`.
- Low-cost fallback is the default skeleton path: video backend off → Ken Burns on stills. ([ADR.md] ADR-0011)
- voice default is narration (`voiceover`); on_camera only when the ReelProfile asks and the backend supports it; never voice-injection lip-sync. ([ADR.md] ADR-0012). Skeleton uses `none` (music bed / silent).
- Deterministic layer covered by real assertions; external model calls mocked. `pytest -q`, `ruff check src tests`, `ruff format src tests`, `mypy` after a series of changes.
- Default locale english/US unless the ReelProfile says otherwise.

## File structure

```
src/reel_gen_agent/generate/
  run_context.py        # resolve output dir from ReelProfile path; RunManifest helpers
  capability.py         # ModelCapability matrix loaded from config/.env (model-agnostic)
  production_plan.py     # ProductionIntent + capability + resources -> ProductionPlan
  subtitles.py          # pilmoji -> transparent subtitle PNG
  backends/
    __init__.py
    video_base.py       # VideoBackend protocol (render_panel)
    ken_burns.py        # KenBurnsBackend: still -> clip via ffmpeg (no external model)
  materials.py          # ReelProfile + ProductionPlan -> Materials (skeleton: ken burns + subtitles)
  assemble.py           # Materials + meta -> final.mp4 (concat, mux, subtitle overlay) + RunManifest update
  describe.py           # ReelProfile + final.mp4 -> UploadKit -> upload.md
  report.py             # gather RunManifest/Conformance/Rubric -> FinalReport -> report.md
  production_graph.py    # orchestrator: plan -> materials -> assemble -> verify(loop) -> describe -> evaluate -> report
tests/
  test_run_context.py
  test_production_plan.py
  test_subtitles.py
  test_ken_burns.py
  test_assemble.py
  test_describe_report.py
  test_production_graph.py
```

Reused as-is: `generate/conformance.py` (`verify_conformance`), `analysis/rubric.py` (`evaluate_video`), `analysis/media_probe.py` (ffprobe). The `execute` CLI command is added to `cli.py`.

---

## Milestone 1 — Walking skeleton (Ken Burns, no API keys)

A hand-written `ReelProfile` whose panels carry `still_image` paths renders to a final mp4 through Ken Burns, gets verified, described, evaluated (VLM mocked), and reported. This proves the whole production graph end to end.

### Task 1: run_context — locate output dir and seed RunManifest

**Files:**
- Create: `src/reel_gen_agent/generate/run_context.py`
- Test: `tests/test_run_context.py`

**Interfaces:**
- Consumes: `ReelProfile` (schema), a profile json path.
- Produces:
  - `output_dir_for(profile_path: str) -> Path` — the directory containing the profile.
  - `new_manifest(profile_path: str, profile: ReelProfile) -> RunManifest` — `run_id` = output dir name, `input_path` = profile_path.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_context.py
from pathlib import Path

from reel_gen_agent.generate.run_context import output_dir_for, new_manifest
from reel_gen_agent.generate.schema import ReelProfile, Objective, ProductSpec


def _profile() -> ReelProfile:
    return ReelProfile(objective=Objective(goal="demo"), product=ProductSpec(name="serum"))


def test_output_dir_is_profile_parent(tmp_path):
    d = tmp_path / "glow-serum-20260701-101010"
    d.mkdir()
    p = d / "ReelProfile-glow-serum-20260701-101010.json"
    p.write_text(_profile().model_dump_json(), encoding="utf-8")
    assert output_dir_for(str(p)) == d


def test_new_manifest_sets_run_id_from_dirname(tmp_path):
    d = tmp_path / "glow-serum-20260701-101010"
    d.mkdir()
    p = d / "ReelProfile-x.json"
    p.write_text(_profile().model_dump_json(), encoding="utf-8")
    m = new_manifest(str(p), _profile())
    assert m.run_id == "glow-serum-20260701-101010"
    assert m.input_path == str(p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_run_context.py -v`
Expected: FAIL (`ModuleNotFoundError: run_context`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/run_context.py
"""execute 산출물 폴더와 RunManifest를 잡는 헬퍼.

execute는 폴더를 만들거나 이름 짓지 않는다. 주어진 ReelProfile이 들어 있는 폴더가
곧 outputs/<run_id>/ 이고, run_id는 그 폴더 이름이다(plan-stage가 만든 규약).
"""

from __future__ import annotations

from pathlib import Path

from .schema import ReelProfile, RunManifest


def output_dir_for(profile_path: str) -> Path:
    """ReelProfile json이 들어 있는 폴더(= outputs/<run_id>/)를 돌려준다."""
    return Path(profile_path).resolve().parent


def new_manifest(profile_path: str, profile: ReelProfile) -> RunManifest:
    """폴더 이름을 run_id로 쓰는 빈 RunManifest를 만든다."""
    return RunManifest(run_id=output_dir_for(profile_path).name, input_path=profile_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_run_context.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/run_context.py tests/test_run_context.py
git commit -m "feat(execute): run_context to locate output dir and seed RunManifest"
```

### Task 2: production_plan — resolve ProductionPlan from intent + capability

**Files:**
- Create: `src/reel_gen_agent/generate/capability.py`, `src/reel_gen_agent/generate/production_plan.py`
- Test: `tests/test_production_plan.py`

**Interfaces:**
- Consumes: `ReelProfile` (has `production_intent`, `meta`, `narration.delivery`, `storyboard`), env mapping.
- Produces:
  - `capability_for(model_id: str) -> ModelCapability` (reads a config table; default Ken Burns capability when model_id is `"ken_burns"`).
  - `resolve_plan(profile: ReelProfile, env: dict[str, str]) -> ProductionPlan`. Rules: if no video backend key present → `video_model="ken_burns"`, `panel_renderers` all `"ken_burns"`, append fallback `"no_video_key->ken_burns"`. voice_strategy: `voiceover` by default; `none` if `delivery == "none"`; `integrated` only if `delivery == "on_camera"` and capability.integrated_voice and (single panel OR model supports consistent multi-cut voice). Otherwise downgrade to `voiceover` and append a fallback note.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_production_plan.py
from reel_gen_agent.generate.production_plan import resolve_plan
from reel_gen_agent.generate.schema import (
    ReelProfile, Objective, ProductSpec, Storyboard, StoryboardPanel, NarrationSpec,
)


def _profile(delivery="voiceover", panels=1) -> ReelProfile:
    sb = Storyboard(panels=[StoryboardPanel(index=i) for i in range(panels)])
    return ReelProfile(
        objective=Objective(goal="demo"),
        product=ProductSpec(name="serum"),
        storyboard=sb,
        narration=NarrationSpec(delivery=delivery),
    )


def test_no_video_key_falls_back_to_ken_burns():
    plan = resolve_plan(_profile(), env={})
    assert plan.video_model == "ken_burns"
    assert plan.panel_renderers == ["ken_burns"]
    assert any("ken_burns" in f for f in plan.fallbacks_applied)


def test_voiceover_is_default_voice_strategy():
    plan = resolve_plan(_profile(delivery="voiceover"), env={})
    assert plan.voice_strategy == "separate_tts"


def test_delivery_none_means_no_voice():
    plan = resolve_plan(_profile(delivery="none"), env={})
    assert plan.voice_strategy == "none"


def test_on_camera_multicut_without_kling_downgrades_to_voiceover():
    plan = resolve_plan(_profile(delivery="on_camera", panels=3), env={})
    assert plan.voice_strategy == "separate_tts"
    assert any("on_camera" in f for f in plan.fallbacks_applied)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_production_plan.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/capability.py
"""모델 능력 표(capability matrix). 코드에 모델을 박지 않고 데이터로 둔다."""

from __future__ import annotations

from .schema import ModelCapability

# 기본 표. 실제 운영 표는 .env/config로 주입·확장한다(모델 비종속).
_MATRIX: dict[str, ModelCapability] = {
    "ken_burns": ModelCapability(
        model_id="ken_burns", lane="local", multishot=True, integrated_voice=False
    ),
}


def capability_for(model_id: str) -> ModelCapability:
    return _MATRIX.get(
        model_id, ModelCapability(model_id=model_id, lane="vertex")
    )
```

```python
# src/reel_gen_agent/generate/production_plan.py
"""ProductionIntent + capability + 가용 리소스 -> ProductionPlan.

이식 가능한 의도(ReelProfile)를 머신 환경에 맞춰 해소하고, 적용한 폴백을 남긴다.
voice 기본은 나레이션(voiceover). on_camera 멀티컷 일관은 Kling O3 Pro만 가능하므로
그 백엔드가 없으면 voiceover로 안전하게 내려간다([ADR.md] ADR-0012).
"""

from __future__ import annotations

from .capability import capability_for
from .schema import ProductionPlan, ReelProfile

_VIDEO_KEYS = ("GOOGLE_CLOUD_PROJECT", "FAL_KEY")  # 하나라도 있으면 영상 백엔드 가능


def _has_video_backend(env: dict[str, str]) -> bool:
    return any(env.get(k) for k in _VIDEO_KEYS)


def resolve_plan(profile: ReelProfile, env: dict[str, str]) -> ProductionPlan:
    fallbacks: list[str] = []
    panels = profile.storyboard.panels or []
    n = max(1, len(panels))

    if _has_video_backend(env):
        video_model = env.get("VEO_MODEL", "veo-3.1-lite-generate-001")
    else:
        video_model = "ken_burns"
        fallbacks.append("no_video_key->ken_burns")
    cap = capability_for(video_model)
    renderers = [video_model if video_model == "ken_burns" else "i2v"] * (1 if video_model == "ken_burns" else n)
    if video_model == "ken_burns":
        renderers = ["ken_burns"] * 1 if n == 1 else ["ken_burns"] * n

    delivery = profile.narration.delivery
    if delivery == "none":
        voice_strategy = "none"
    elif delivery == "on_camera":
        kling_multicut = cap.integrated_voice and (n == 1 or cap.lane == "fal")
        if kling_multicut:
            voice_strategy = "integrated"
        else:
            voice_strategy = "separate_tts"
            fallbacks.append("on_camera_multicut_needs_kling->voiceover")
    else:  # voiceover (기본)
        voice_strategy = "separate_tts"

    return ProductionPlan(
        video_model=video_model,
        capability=cap,
        voice_strategy=voice_strategy,
        multishot=cap.multishot,
        key_image_per_cut=(video_model != "ken_burns"),
        panel_renderers=renderers,
        bgm=profile.production_intent.bgm_pref,
        sfx=profile.production_intent.sfx_pref,
        fallbacks_applied=fallbacks,
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_production_plan.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/capability.py src/reel_gen_agent/generate/production_plan.py tests/test_production_plan.py
git commit -m "feat(execute): resolve ProductionPlan from intent and capability matrix"
```

### Task 3: subtitles — transparent PNG with pilmoji

**Files:**
- Create: `src/reel_gen_agent/generate/subtitles.py`
- Test: `tests/test_subtitles.py`

**Interfaces:**
- Produces: `render_subtitle_png(text: str, width: int, height: int, out_path: str) -> str` — writes a transparent RGBA PNG sized to the frame and returns the path. Empty text writes a fully transparent image.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_subtitles.py
from PIL import Image

from reel_gen_agent.generate.subtitles import render_subtitle_png


def test_writes_rgba_png_of_frame_size(tmp_path):
    out = tmp_path / "sub.png"
    p = render_subtitle_png("Glowing skin ✨", 1080, 1920, str(out))
    img = Image.open(p)
    assert img.size == (1080, 1920)
    assert img.mode == "RGBA"


def test_empty_text_is_fully_transparent(tmp_path):
    out = tmp_path / "empty.png"
    render_subtitle_png("", 540, 960, str(out))
    img = Image.open(out).convert("RGBA")
    # 알파 최대값이 0이면 완전히 투명하다.
    assert max(px[3] for px in img.getdata()) == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_subtitles.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/subtitles.py
"""자막 PNG 렌더. Pillow 위에 pilmoji로 컬러 이모지를 보존한 투명 PNG를 만든다.

자막 텍스트·타이밍은 스토리보드 패널에서 오므로 음성 인식·강제 정렬이 필요 없다.
(docs/pipeline-design.md "자막과 이모지")
"""

from __future__ import annotations

from PIL import Image, ImageFont
from pilmoji import Pilmoji


def render_subtitle_png(text: str, width: int, height: int, out_path: str) -> str:
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if text:
        font = ImageFont.load_default(size=max(28, width // 18))
        with Pilmoji(img) as p:
            tw, th = p.getsize(text, font=font)
            x = max(0, (width - tw) // 2)
            y = int(height * 0.78)
            p.text((x, y), text, fill=(255, 255, 255, 255), font=font)
    img.save(out_path)
    return out_path
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_subtitles.py -v`
Expected: PASS. (If `ImageFont.load_default(size=...)` is unavailable in the installed Pillow, fall back to `ImageFont.load_default()` with no size arg — adjust and re-run.)

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/subtitles.py tests/test_subtitles.py
git commit -m "feat(execute): pilmoji transparent subtitle PNG renderer"
```

### Task 4: ken_burns backend — still → clip

**Files:**
- Create: `src/reel_gen_agent/generate/backends/__init__.py`, `backends/video_base.py`, `backends/ken_burns.py`
- Test: `tests/test_ken_burns.py`

**Interfaces:**
- Produces:
  - `video_base.VideoBackend` (Protocol): `render_panel(still_path: str, duration_sec: float, width: int, height: int, fps: int, out_path: str) -> str`.
  - `ken_burns.KenBurnsBackend` implementing it with ffmpeg `zoompan`. Output mp4 (H.264/AAC silent track) at the requested duration/size.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ken_burns.py
from PIL import Image

from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend
from reel_gen_agent.analysis.media_probe import probe_container


def _still(tmp_path):
    p = tmp_path / "still.png"
    Image.new("RGB", (1080, 1920), (200, 120, 160)).save(p)
    return str(p)


def test_ken_burns_makes_clip_of_requested_duration(tmp_path):
    out = tmp_path / "clip.mp4"
    KenBurnsBackend().render_panel(_still(tmp_path), 2.0, 1080, 1920, 30, str(out))
    meta = probe_container(str(out))
    assert out.exists()
    assert abs(meta.duration_sec - 2.0) < 0.3
    assert (meta.width, meta.height) == (1080, 1920)
```

(Confirm the actual `probe_container` symbol/fields in `analysis/media_probe.py` and adjust attribute names if they differ.)

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_ken_burns.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/backends/__init__.py
```

```python
# src/reel_gen_agent/generate/backends/video_base.py
"""영상 백엔드 인터페이스. 패널 하나를 클립으로 만든다.

스키마 경계 뒤의 어댑터라, Veo/Kling/켄 번스가 같은 시그니처를 공유한다.
"""

from __future__ import annotations

from typing import Protocol


class VideoBackend(Protocol):
    def render_panel(
        self,
        still_path: str,
        duration_sec: float,
        width: int,
        height: int,
        fps: int,
        out_path: str,
    ) -> str: ...
```

```python
# src/reel_gen_agent/generate/backends/ken_burns.py
"""켄 번스 폴백 백엔드. 스틸을 천천히 줌/팬해 클립을 만든다(외부 모델 없음).

영상 모델 예산이 없어도 파이프라인이 끝까지 도는 워킹 스켈레톤의 기본 경로다
([ADR.md] ADR-0011).
"""

from __future__ import annotations

import subprocess


class KenBurnsBackend:
    def render_panel(
        self,
        still_path: str,
        duration_sec: float,
        width: int,
        height: int,
        fps: int,
        out_path: str,
    ) -> str:
        total = max(1, int(round(duration_sec * fps)))
        # 스틸을 살짝 줌인하며 width x height로 출력. 무음 오디오 트랙을 붙여 mux 호환.
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"zoompan=z='min(zoom+0.0005,1.1)':d={total}:s={width}x{height}:fps={fps}"
        )
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", still_path,
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", vf, "-t", f"{duration_sec}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-shortest", out_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_ken_burns.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/backends tests/test_ken_burns.py
git commit -m "feat(execute): VideoBackend interface and Ken Burns fallback renderer"
```

### Task 5: assemble — concat + subtitle overlay + mux → final.mp4

**Files:**
- Create: `src/reel_gen_agent/generate/assemble.py`
- Test: `tests/test_assemble.py`

**Interfaces:**
- Consumes: `Materials` (shot_clips, subtitle_pngs, bgm_audio), `InputMeta`.
- Produces: `assemble(materials: Materials, meta: InputMeta, out_path: str) -> str` — concat shot clips in order, overlay each subtitle PNG on its clip's time window, mux bgm if present (else keep silent), encode mp4 H.264/AAC at meta size/fps, return out_path.

- [ ] **Step 1: Write the failing test** (uses two real Ken Burns clips so the test is deterministic and key-free)

```python
# tests/test_assemble.py
from PIL import Image

from reel_gen_agent.generate.backends.ken_burns import KenBurnsBackend
from reel_gen_agent.generate.assemble import assemble
from reel_gen_agent.generate.schema import Materials, InputMeta
from reel_gen_agent.analysis.media_probe import probe_container


def _clip(tmp_path, name, dur):
    still = tmp_path / f"{name}.png"
    Image.new("RGB", (540, 960), (180, 140, 200)).save(still)
    out = tmp_path / f"{name}.mp4"
    KenBurnsBackend().render_panel(str(still), dur, 540, 960, 30, str(out))
    return str(out)


def test_assemble_concats_to_expected_duration(tmp_path):
    mats = Materials(shot_clips=[_clip(tmp_path, "a", 1.0), _clip(tmp_path, "b", 1.0)])
    out = tmp_path / "final.mp4"
    assemble(mats, InputMeta(width=540, height=960), str(out))
    meta = probe_container(str(out))
    assert out.exists()
    assert abs(meta.duration_sec - 2.0) < 0.4
    assert (meta.width, meta.height) == (540, 960)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_assemble.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write minimal implementation** (concat via ffmpeg concat demuxer; overlay/mux folded in)

```python
# src/reel_gen_agent/generate/assemble.py
"""결정론 조립. 샷 클립 concat + 자막 오버레이 + 오디오 mux -> final.mp4.

같은 Materials는 같은 결과를 낸다(재현성). 컨테이너/코덱은 trd.md 가드레일(mp4/H.264/AAC).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .schema import InputMeta, Materials


def assemble(materials: Materials, meta: InputMeta, out_path: str) -> str:
    if not materials.shot_clips:
        raise ValueError("assemble: shot_clips is empty")
    # 워킹 스켈레톤: concat demuxer로 클립을 잇는다. (자막 오버레이/믹스는 다음 태스크에서)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        for clip in materials.shot_clips:
            f.write(f"file '{Path(clip).resolve()}'\n")
        listfile = f.name
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(meta.fps),
        "-c:a", "aac", out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_assemble.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/assemble.py tests/test_assemble.py
git commit -m "feat(execute): ffmpeg assemble (concat) to final mp4"
```

> Note: subtitle overlay (`overlay` filter per panel time window) and bgm mux are added in Milestone 2 Task 11, keeping this task's deliverable a clean concat.

### Task 6: materials — ReelProfile + ProductionPlan → Materials (Ken Burns path)

**Files:**
- Create: `src/reel_gen_agent/generate/materials.py`
- Test: `tests/test_materials.py`

**Interfaces:**
- Consumes: `ReelProfile`, `ProductionPlan`, output dir.
- Produces: `build_materials(profile, plan, out_dir) -> Materials`. Skeleton: for each panel with a `still_image`, Ken Burns render to `out_dir/panels/clip_<i>.mp4`; render a subtitle PNG per panel into `out_dir/panels/sub_<i>.png`. voice/bgm/sfx left empty (skeleton).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_materials.py
from PIL import Image

from reel_gen_agent.generate.materials import build_materials
from reel_gen_agent.generate.production_plan import resolve_plan
from reel_gen_agent.generate.schema import (
    ReelProfile, Objective, ProductSpec, InputMeta, Storyboard, StoryboardPanel,
)


def _profile(tmp_path):
    stills = []
    for i in range(2):
        s = tmp_path / f"s{i}.png"
        Image.new("RGB", (540, 960), (160, 120, 180)).save(s)
        stills.append(str(s))
    panels = [
        StoryboardPanel(index=i, t_start=i * 1.0, t_end=i * 1.0 + 1.0,
                        subtitle_text=f"line {i}", still_image=stills[i])
        for i in range(2)
    ]
    return ReelProfile(
        objective=Objective(goal="demo"), product=ProductSpec(name="serum"),
        meta=InputMeta(width=540, height=960), storyboard=Storyboard(panels=panels),
    )


def test_build_materials_makes_a_clip_and_subtitle_per_panel(tmp_path):
    profile = _profile(tmp_path)
    plan = resolve_plan(profile, env={})  # ken_burns
    mats = build_materials(profile, plan, str(tmp_path / "run"))
    assert len(mats.shot_clips) == 2
    assert len(mats.subtitle_pngs) == 2
    assert all((tmp_path / "run").exists() for _ in [0])
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_materials.py -v` → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/materials.py
"""ReelProfile + ProductionPlan -> Materials. 워킹 스켈레톤은 켄 번스 + 자막만 만든다.

영상 백엔드/voice/bgm은 Milestone 2에서 같은 인터페이스 뒤에 붙인다.
"""

from __future__ import annotations

from pathlib import Path

from .backends.ken_burns import KenBurnsBackend
from .schema import Materials, ProductionPlan, ReelProfile
from .subtitles import render_subtitle_png


def build_materials(profile: ReelProfile, plan: ProductionPlan, out_dir: str) -> Materials:
    panels_dir = Path(out_dir) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    m = profile.meta
    backend = KenBurnsBackend()
    clips: list[str] = []
    subs: list[str] = []
    for panel in profile.storyboard.panels:
        dur = max(0.5, (panel.t_end or 0.0) - (panel.t_start or 0.0)) or 2.0
        clip = str(panels_dir / f"clip_{panel.index}.mp4")
        backend.render_panel(panel.still_image, dur, m.width, m.height, m.fps, clip)
        clips.append(clip)
        sub = str(panels_dir / f"sub_{panel.index}.png")
        render_subtitle_png(panel.subtitle_text or "", m.width, m.height, sub)
        subs.append(sub)
    return Materials(shot_clips=clips, subtitle_pngs=subs)
```

- [ ] **Step 4: Run to verify it passes** — `uv run pytest tests/test_materials.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/materials.py tests/test_materials.py
git commit -m "feat(execute): build Ken Burns materials (clips + subtitle PNGs) per panel"
```

### Task 7: describe + report — UploadKit and FinalReport renderers

**Files:**
- Create: `src/reel_gen_agent/generate/describe.py`, `src/reel_gen_agent/generate/report.py`
- Test: `tests/test_describe_report.py`

**Interfaces:**
- Produces:
  - `describe.build_upload_kit(profile: ReelProfile) -> UploadKit` (deterministic skeleton: title from objective/product, outline from panel timings, caption from key_message + product name).
  - `describe.render_upload_md(kit: UploadKit, out_path: str) -> str`.
  - `report.build_final_report(run_id, profile, manifest, conformance: dict, rubric: dict) -> FinalReport` (user_input echo, node_prompts from manifest.nodes, node_flow, models_used from manifest.production_plan, bgm_source).
  - `report.render_report_md(report: FinalReport, out_path: str) -> str` — layout: user input first, node prompts last.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_describe_report.py
from reel_gen_agent.generate.describe import build_upload_kit, render_upload_md
from reel_gen_agent.generate.report import build_final_report, render_report_md
from reel_gen_agent.generate.schema import (
    ReelProfile, Objective, ProductSpec, Storyboard, StoryboardPanel,
    RunManifest, NodeRun, ProductionPlan,
)


def _profile():
    return ReelProfile(
        objective=Objective(goal="serum glow reel", key_message="dewy in 15s"),
        product=ProductSpec(name="Glow Serum"),
        storyboard=Storyboard(panels=[StoryboardPanel(index=0, t_start=0, t_end=2)]),
    )


def test_upload_kit_has_title_and_outline(tmp_path):
    kit = build_upload_kit(_profile())
    assert kit.title
    assert len(kit.outline) == 1
    assert "Glow Serum" in kit.caption
    out = tmp_path / "upload.md"
    render_upload_md(kit, str(out))
    assert out.read_text(encoding="utf-8").strip()


def test_final_report_md_puts_user_input_first_and_prompts_last(tmp_path):
    profile = _profile()
    manifest = RunManifest(
        run_id="glow-20260701-101010",
        nodes=[NodeRun(name="video", prompt="serum on a table")],
        production_plan=ProductionPlan(video_model="ken_burns", voice_strategy="none"),
    )
    rep = build_final_report("glow-20260701-101010", profile, manifest, {"passed": True}, {"gated_score": 71})
    out = tmp_path / "report.md"
    render_report_md(rep, str(out))
    text = out.read_text(encoding="utf-8")
    assert text.index("serum glow reel") < text.index("serum on a table")
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_describe_report.py -v` → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/describe.py
"""describe 노드: verify 통과 후 업로드용 자산(UploadKit -> upload.md)."""

from __future__ import annotations

from .schema import OutlineItem, ReelProfile, UploadKit


def _mmss(t: float) -> str:
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def build_upload_kit(profile: ReelProfile) -> UploadKit:
    title = profile.objective.key_message or f"{profile.product.name} | {profile.objective.goal}"
    outline = [
        OutlineItem(timecode=_mmss(p.t_start or 0.0), content=(p.beat or p.subtitle_text or f"shot {p.index}"))
        for p in profile.storyboard.panels
    ]
    caption = f"{profile.objective.goal} — {profile.product.name}."
    if profile.objective.key_message:
        caption = f"{profile.objective.key_message} {caption}"
    return UploadKit(title=title, outline=outline, caption=caption)


def render_upload_md(kit: UploadKit, out_path: str) -> str:
    lines = [f"# {kit.title}", "", "## 영상 구조"]
    lines += [f"- `{o.timecode}` {o.content}" for o in kit.outline]
    lines += ["", "## 본문", kit.caption]
    if kit.hashtags:
        lines += ["", " ".join(f"#{h}" for h in kit.hashtags)]
    out = "\n".join(lines) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    return out_path
```

```python
# src/reel_gen_agent/generate/report.py
"""report 노드: 회차 종합 리포트(FinalReport -> report.md).

레이아웃: 유저 입력(앞단) -> 의견 -> 노드 흐름 -> 모델 -> bgm -> eval -> 예측 ->
노드별 프롬프트(뒤). 렌더링은 결정론, final_opinion/viral_prediction만 LLM(여기선 빈값).
"""

from __future__ import annotations

from .schema import (
    BgmReport, FinalReport, NodePrompt, ReelProfile, RunManifest, UserInputEcho,
)


def build_final_report(
    run_id: str,
    profile: ReelProfile,
    manifest: RunManifest,
    conformance: dict,
    rubric: dict,
) -> FinalReport:
    echo = UserInputEcho(
        objective=profile.objective.goal,
        product_input=profile.product.name,
        reference_ref=profile.provenance.reference_ref,
    )
    prompts = [
        NodePrompt(node=nr.name, prompt=nr.prompt)
        for nr in manifest.nodes
        if nr.prompt
    ]
    plan = manifest.production_plan
    models = {"video": plan.video_model} if plan else {}
    bgm = BgmReport(kind=(plan.bgm if plan else "none"))
    return FinalReport(
        run_id=run_id,
        user_input=echo,
        node_prompts=prompts,
        node_flow=[nr.name for nr in manifest.nodes],
        models_used=models,
        bgm_source=bgm,
        conformance=conformance,
        rubric=rubric,
    )


def render_report_md(report: FinalReport, out_path: str) -> str:
    e = report.user_input
    lines = [
        f"# 최종 리포트 — {report.run_id}",
        "",
        "## 유저 입력",
        f"- 목적: {e.objective}",
        f"- 제품: {e.product_input or '-'}",
        f"- 레퍼런스: {e.reference_ref or '-'}",
        "",
        "## 최종 의견",
        report.final_opinion or "(미작성)",
        "",
        "## 노드 흐름",
        " -> ".join(report.node_flow) or "-",
        "",
        "## 사용 모델",
        ", ".join(f"{k}={v}" for k, v in report.models_used.items()) or "-",
        "",
        f"## BGM\n- {report.bgm_source.kind}",
        "",
        f"## 평가\n- conformance: {report.conformance}\n- rubric: {report.rubric}",
        "",
        "## 바이럴 예측",
        report.viral_prediction or "(미작성)",
        "",
        "## 노드별 프롬프트",
    ]
    lines += [f"### {p.node}\n{p.prompt}" for p in report.node_prompts] or ["-"]
    out = "\n".join(lines) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    return out_path
```

- [ ] **Step 4: Run to verify it passes** — `uv run pytest tests/test_describe_report.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/describe.py src/reel_gen_agent/generate/report.py tests/test_describe_report.py
git commit -m "feat(execute): describe (UploadKit) and report (FinalReport) renderers"
```

### Task 8: production orchestrator + execute CLI (skeleton end-to-end)

**Files:**
- Create: `src/reel_gen_agent/generate/production_graph.py`
- Modify: `src/reel_gen_agent/cli.py` (add `execute` command)
- Test: `tests/test_production_graph.py`

**Interfaces:**
- Consumes: everything above + `verify_conformance` (conformance.py) + `evaluate_video` (rubric.py).
- Produces: `run_production(profile_path: str, *, use_vlm: bool = True) -> RunManifest`. Order: load ReelProfile → resolve_plan → build_materials → assemble → verify (record result; on fail in skeleton, still continue but mark) → describe (upload.md) → evaluate (rubric; gemini mocked/off) → report (report.md). Writes final.mp4, upload.md, report.md, run.json into the output dir.

- [ ] **Step 1: Write the failing test** (whole skeleton, VLM/rubric mocked)

```python
# tests/test_production_graph.py
from unittest.mock import patch
from PIL import Image

from reel_gen_agent.generate.production_graph import run_production
from reel_gen_agent.generate.schema import (
    ReelProfile, Objective, ProductSpec, InputMeta, Storyboard, StoryboardPanel,
)


def _write_profile(tmp_path):
    d = tmp_path / "demo-20260701-101010"
    d.mkdir()
    stills = []
    for i in range(2):
        s = d / f"s{i}.png"
        Image.new("RGB", (540, 960), (170, 130, 190)).save(s)
        stills.append(str(s))
    panels = [StoryboardPanel(index=i, t_start=i, t_end=i + 1, subtitle_text=f"l{i}",
                              still_image=stills[i]) for i in range(2)]
    profile = ReelProfile(objective=Objective(goal="demo reel"), product=ProductSpec(name="serum"),
                          meta=InputMeta(width=540, height=960), storyboard=Storyboard(panels=panels))
    p = d / "ReelProfile-demo-20260701-101010.json"
    p.write_text(profile.model_dump_json(), encoding="utf-8")
    return str(p), d


def test_skeleton_runs_end_to_end(tmp_path):
    profile_path, d = _write_profile(tmp_path)
    with patch("reel_gen_agent.generate.production_graph.evaluate_video") as mock_eval, \
         patch("reel_gen_agent.generate.production_graph.verify_conformance") as mock_verify:
        mock_verify.return_value = type("R", (), {"passed": True, "model_dump": lambda self: {"passed": True}})()
        mock_eval.return_value = type("E", (), {"model_dump": lambda self: {"gated_score": 70}})()
        manifest = run_production(profile_path, use_vlm=False)
    assert (d / "final.mp4").exists()
    assert (d / "report.md").exists()
    assert (d / "upload.md").exists()
    assert manifest.final_video.endswith("final.mp4")
```

(Confirm `verify_conformance` / `evaluate_video` return types and adapt the mock to their real attributes.)

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_production_graph.py -v` → FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
# src/reel_gen_agent/generate/production_graph.py
"""execute 오케스트레이터(워킹 스켈레톤). 그래프 위상은 정적, 라우팅은 데이터 기반.

흐름: load -> production_plan -> materials -> assemble -> verify -> describe -> evaluate -> report.
지금은 순차 함수다. LangGraph 노드/Send 팬아웃/verify 리페어 루프는 Milestone 2에서 얹는다.
"""

from __future__ import annotations

from pathlib import Path

from ..analysis.rubric import evaluate_video
from .assemble import assemble
from .conformance import verify_conformance
from .describe import build_upload_kit, render_upload_md
from .materials import build_materials
from .production_plan import resolve_plan
from .report import build_final_report, render_report_md
from .run_context import new_manifest, output_dir_for
from .schema import NodeRun, ReelProfile


def run_production(profile_path: str, *, use_vlm: bool = True) -> RunManifest:  # noqa: F821
    profile = ReelProfile.model_validate_json(Path(profile_path).read_text(encoding="utf-8"))
    out_dir = output_dir_for(profile_path)
    manifest = new_manifest(profile_path, profile)

    plan = resolve_plan(profile, env={})
    manifest.production_plan = plan
    manifest.nodes.append(NodeRun(name="production_plan"))

    materials = build_materials(profile, plan, str(out_dir))
    manifest.nodes.append(NodeRun(name="materials", artifacts=materials.shot_clips))

    final_video = str(out_dir / "final.mp4")
    assemble(materials, profile.meta, final_video)
    manifest.final_video = final_video
    manifest.panel_segments = materials.shot_clips
    manifest.nodes.append(NodeRun(name="assemble", artifacts=[final_video]))

    conf = verify_conformance(final_video)  # 레퍼런스 없는 intrinsic 체크
    conf_dump = conf.model_dump()
    manifest.nodes.append(NodeRun(name="verify"))

    kit = build_upload_kit(profile)
    render_upload_md(kit, str(out_dir / "upload.md"))
    manifest.nodes.append(NodeRun(name="describe", artifacts=[str(out_dir / "upload.md")]))

    rubric_dump: dict = {}
    if use_vlm:
        rubric_dump = evaluate_video(final_video).model_dump()
    manifest.nodes.append(NodeRun(name="evaluate"))

    report = build_final_report(manifest.run_id, profile, manifest, conf_dump, rubric_dump)
    render_report_md(report, str(out_dir / "report.md"))
    manifest.nodes.append(NodeRun(name="report", artifacts=[str(out_dir / "report.md")]))

    (out_dir / "run.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest
```

Add the `RunManifest` import (fix the `# noqa`): `from .schema import NodeRun, ReelProfile, RunManifest` and drop the noqa.

Then the CLI command:

```python
# add to src/reel_gen_agent/cli.py
from .generate.production_graph import run_production


@app.command()
def execute(
    profile: str = typer.Argument(..., help="ReelProfile JSON 경로"),
    no_vlm: bool = typer.Option(False, "--no-vlm", help="rubric 채점을 건너뛴다."),
) -> None:
    """ReelProfile을 받아 Production을 돌려 outputs/<run_id>/에 영상·리포트를 만든다."""
    from pathlib import Path as _P

    if not _P(profile).exists():
        typer.echo(f"파일 없음: {profile}", err=True)
        raise typer.Exit(code=1)
    manifest = run_production(profile, use_vlm=not no_vlm)
    typer.echo(f"영상: {manifest.final_video}", err=True)
```

- [ ] **Step 4: Run to verify it passes** — `uv run pytest tests/test_production_graph.py -v` → PASS. Then `uv run pytest -q` (full) and `uv run ruff check src tests && uv run mypy`.

- [ ] **Step 5: Commit**

```bash
git add src/reel_gen_agent/generate/production_graph.py src/reel_gen_agent/cli.py tests/test_production_graph.py
git commit -m "feat(execute): production orchestrator and execute CLI (walking skeleton)"
```

**Milestone 1 done:** `uv run reel-gen execute <ReelProfile.json> --no-vlm` produces `final.mp4`, `upload.md`, `report.md`, `run.json` with zero API keys.

---

## Milestone 2 — Deepen (behind the same interfaces)

Each task keeps the schema boundary and adds a focused capability. Follow the same TDD rhythm (failing test → run → implement → run → commit). Mock all external model calls; key-absent paths must `skip`/fallback, never crash.

### Task 9: Veo video backend (Vertex lane)
- **Files:** Create `backends/veo.py` (implements `VideoBackend.render_panel` via `google-genai` Vertex `generate_videos`, GCS download via `google-cloud-storage`). Modify `materials.py` to pick backend from `ProductionPlan.video_model`.
- **Interface:** same `render_panel` signature; reads `VEO_MODEL`, `GOOGLE_CLOUD_PROJECT`, `VEO_OUTPUT_GCS_URI` from env.
- **Test:** mock the genai client; assert `render_panel` calls it with the still as image input + panel prompt and writes the downloaded mp4. With no Vertex creds, `resolve_plan` already routes to Ken Burns, so this test only runs the mocked client path.
- **Contract:** [ai-model-records.md](../../../specs/ai-model-records.md) §4 (Veo 3.1 Fast default, Vertex only, native audio via `generate_audio=True` when `voice_strategy=integrated`).

### Task 10: Kling backend (fal lane, opt-in)
- **Files:** Create `backends/kling.py` (`fal-client`, `o3/pro/reference-to-video` and `o3 image-to-video`). Inject character/product catalog images from `profile.asset_bible` as references.
- **Interface:** same `render_panel`, plus `render_multishot(panels, refs) -> list[str]` for multishot.
- **Test:** mock fal client; assert reference images and per-panel prompts are passed; assert multi-cut+on_camera path selects this backend.
- **Contract:** [ai-model-records.md] §4/§6 — Kling O3 Pro is the only multi-cut consistent-voice lip-sync path.

### Task 11: assemble — subtitle overlay + audio mux
- **Files:** Modify `assemble.py`.
- **Add:** overlay each `subtitle_pngs[i]` on clip i's time window (ffmpeg `overlay` with `enable='between(t,start,end)'` on the concatenated timeline), and mux `materials.bgm_audio`/`voice_audio` (ffmpeg `amix`), normalize loudness toward the conformance LUFS target.
- **Test:** build two Ken Burns clips + two subtitle PNGs + a generated silent/synthetic wav; assert output has the subtitle stream burned (pixel check a known subtitle region differs from no-subtitle render) and an audio stream present (`probe_container`).

### Task 12: voice material (narration TTS)
- **Files:** Create `backends/voice_tts.py` (ElevenLabs preferred, Google TTS Chirp 3 fallback), modify `materials.py` to fill `Materials.voice_audio` when `voice_strategy=separate_tts`.
- **Interface:** `synthesize(lines: list[NarrationLine], voice: VoiceSpec, out_path) -> str`. Voice attributes derived from `ModelSpec` upstream (already in `NarrationSpec.voice`).
- **Test:** mock the TTS client; assert one continuous track is produced from the panel lines and that timing alignment metadata is returned for assemble.
- **Contract:** [ADR.md] ADR-0012 — narration default; never inject voice for lip-sync.

### Task 13: bgm material (Lyria) + sfx
- **Files:** Create `backends/music.py` (Lyria via genai; or pass-through provided file), modify `materials.py`.
- **Test:** mock client; `bgm="gen"` calls Lyria with `MusicSpec` mood/tempo; `bgm="file"` copies the provided file; `bgm="none"` leaves silent.

### Task 14: verify→repair loop + LangGraph wiring
- **Files:** Create `gates.py` is owned by plan-stage; here add `repair_router` logic in `production_graph.py` and migrate the sequential orchestrator to a LangGraph `StateGraph` with `Send` fan-out for materials and a bounded verify→repair cycle (`repair_count` cap).
- **Interface:** map conformance defect categories → target node (weak shot → re-render that panel; subtitle position → re-assemble; loudness → re-mux). On cap exceeded, finalize with failure + last report.
- **Test:** feed a synthetic conformance result that fails once then passes; assert exactly one repair iteration ran and the targeted node re-executed; assert cap stops an always-failing case.
- **Contract:** [workflows.md](../../../specs/workflows.md) Phase 2, [conformance-gate.md](../../../specs/conformance-gate.md).

### Task 15: trace + logging (local JSONL, Langfuse optional)
- **Files:** Create `obs/trace.py` (TraceEmitter, LocalJsonlSink always-on, LangfuseSink when `LANGFUSE_*`), wire emits into `production_graph.py` nodes and record `NodeRun.prompt`.
- **Test:** assert `logs/<session_id>/<run_id>/trace.jsonl` is written with no keys; assert LangfuseSink is inert without env; assert key/token redaction.
- **Contract:** [logging-strategy.md](../../../specs/logging-strategy.md).

---

## Self-review notes

- Spec coverage: production_planner (T2), materials/parallel (T6,T9-T13), assemble (T5,T11), verify loop (T14), describe (T7), evaluate (T8), report (T7,T8), outputs 3-file deliverable (T8), trace (T15) — all mapped.
- The skeleton (T1-T8) runs with zero keys via Ken Burns; real backends (T9,T10,T12,T13) are mocked in tests.
- Type consistency: `VideoBackend.render_panel` signature is identical across Ken Burns/Veo/Kling; `Materials`/`ProductionPlan`/`RunManifest`/`FinalReport` come from the shared `generate/schema.py` and are not redefined here.
- Before T9 onward, confirm exact symbols in `analysis/media_probe.py`, `generate/conformance.py` (`verify_conformance` return type), `analysis/rubric.py` (`evaluate_video` return type) and adapt the mocks/attribute names shown above.
