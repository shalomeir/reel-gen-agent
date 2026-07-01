#!/usr/bin/env python
"""레퍼런스 mp4를 거꾸로 ReelProfile(핵심만) + 생성 에셋 이미지로 환원한다.

분석↔기획 분리를 "레퍼런스 영상을 ReelProfile로 되돌린다"로 시연하는 단발 유틸이다.
영상 한 편당:
  1) analyze_video()로 최신 VideoProfile(컷/팔레트/자막/보이스/음악/후크/톤)을 뽑고,
  2) Gemini 멀티모달 1콜로 제품/캐릭터/환경/후크유형/목적을 구조화 추출하고,
  3) 제품은 영상에서 프레임을 캡처해 나노바나나(gemini image)로 카탈로그 컷을,
     캐릭터는 추출한 외형 텍스트만으로 나노바나나 text-to-image로 인물 컷을 만들고,
  4) 위를 합쳐 ReelProfile JSON(핵심만)을 조립해 저장한다.

이미지 백엔드는 analysis.gemini_client의 select_backend/make_client를 재사용한다
(Vertex 우선, GEMINI 키 폴백). 실행:
    .venv/bin/python utils/build-reference-reelprofile.py <video.mp4> [<video2.mp4> ...]

각 영상은 outputs/reference-reelprofiles/<파일이름>/ 아래에 ReelProfile.json과 에셋
이미지로 환원된다.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 패키지(설치된 reel_gen_agent)에서 끌어온다.
from reel_gen_agent.analysis.analyze import analyze_video
from reel_gen_agent.analysis.gemini_client import (
    make_client,
    resolve_model,
    run_multimodal,
    select_backend,
)
from reel_gen_agent.analysis.profile import VideoProfile
from reel_gen_agent.generate.schema import (
    HOOK_TYPES,
    AssetBible,
    CharacterProfile,
    CutRhythm,
    EnvironmentSpec,
    HookCandidate,
    InputMeta,
    ModelSpec,
    MusicSpec,
    NarrationSpec,
    Objective,
    ProductProfile,
    ProductSpec,
    Provenance,
    ReelProfile,
    Storyboard,
    StyleDimensions,
    SubtitleSpec,
    VoiceSpec,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_ROOT = REPO_ROOT / "outputs" / "reference-reelprofiles"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"


def _slug(name: str) -> str:
    """파일 stem을 출력 폴더명으로 쓸 안전한 슬러그로 바꾼다."""
    slug = re.sub(r"[^0-9A-Za-z._-]+", "-", name).strip("-")
    return slug or "reel"


# 모델이 빈 값 대신 흘리는 sentinel 문자열. 진짜 None으로 정규화한다.
_SENTINELS = {"", "null", "none", "n/a", "na", "unknown", "-"}


def _clean(value: str | None) -> str | None:
    """sentinel 문자열을 None으로 바꾼다. 그 외는 원본 유지."""
    if value is None:
        return None
    return None if value.strip().lower() in _SENTINELS else value


# --- Gemini 구조화 추출 스키마 -------------------------------------------------


class AssetExtraction(BaseModel):
    """영상에서 ReelProfile 조립에 필요한 비주얼·기획 필드를 한 번에 뽑는다."""

    product_name: str = ""
    product_category: str = ""  # 예: skincare_efficacy / launch / routine ...
    product_packaging: str = ""  # 패키지 외형(카탈로그 이미지 프롬프트 재료)
    product_usp: str = ""
    product_spec: str = ""  # 크기/제형/구성
    product_affordances: list[str] = Field(default_factory=list)  # 가능 행동
    # 제품이 화면에 가장 또렷이 보이는 시점(초). 이 프레임을 카탈로그 참조로 캡처한다.
    product_best_timestamp_sec: float = 0.0

    character_present: bool = True
    character_name: str = ""
    character_age: str = ""  # 예: mid-20s
    character_gender: str = ""
    character_look: str = ""  # 얼굴·헤어·피부·분위기 상세(텍스트→이미지 재료)
    character_body: str = ""
    character_wardrobe: str = ""

    environment_location: str = ""
    environment_setting: str = ""
    environment_lighting: str = ""
    environment_mood: str = ""

    hook_type: str = ""  # H1~H12 중 하나
    objective_goal: str = ""
    objective_video_type: str = ""  # 광고/언박싱/튜토리얼/후기 ...
    objective_target_audience: str = ""
    objective_key_message: str = ""


_EXTRACT_PROMPT = (
    "You are reverse-engineering a short-form vertical product video into a reusable "
    "creative brief. Watch the whole clip (visuals, on-screen text, audio) and fill "
    "every field of the schema.\n"
    "- product_best_timestamp_sec: the second where the product itself is shown most "
    "clearly and fills the frame best (a clean still we can crop into a catalog shot).\n"
    "- character_look: describe the on-camera person in enough visual detail that an "
    "image model could recreate a similar (not identical) person from text alone: face "
    "shape, skin, hair, age range, vibe. Do not name a real person.\n"
    "- product_category: choose the closest of skincare_efficacy, launch, routine, "
    "info, demo, lifestyle.\n"
    "- hook_type: classify the first 3 seconds as one of "
    + ", ".join(f"{k} ({v['label']})" for k, v in HOOK_TYPES.items())
    + ".\nReturn JSON only."
)


# --- 나노바나나(Gemini image) 호출 --------------------------------------------


def _image_selections() -> list[tuple[str, dict]]:
    """이미지 생성에 시도할 백엔드를 순서대로 모은다(중복 제거).

    select_backend의 결정(Vertex 우선)을 먼저 쓰고, GEMINI 키가 있으면 폴백으로 둔다.
    """
    selections: list[tuple[str, dict]] = []
    primary = select_backend()
    if primary:
        selections.append(primary)
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key and not any(s[0] == "gemini" for s in selections):
        selections.append(("gemini", {"api_key": key}))
    return selections


def _extract_image_bytes(response) -> bytes | None:
    """generate_content 응답에서 첫 인라인 이미지 바이트를 꺼낸다."""
    for cand in getattr(response, "candidates", None) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline else None
            if data:
                # SDK 버전에 따라 bytes 또는 base64 문자열로 온다.
                return base64.b64decode(data) if isinstance(data, str) else data
    return None


def generate_image(prompt: str, ref_image: Path | None, model: str) -> bytes | None:
    """나노바나나로 이미지를 생성해 바이트로 반환한다. 끝까지 실패하면 None.

    제품 카탈로그는 영상 캡처 프레임(ref_image)을 참조로 같이 넣고, 캐릭터는 텍스트
    프롬프트만 넣는다. 백엔드/응답 모달리티 조합을 차례로 시도한다.
    """
    selections = _image_selections()
    if not selections:
        print("[image] genai 자격 없음 - 이미지 생성 건너뜀", file=sys.stderr)
        return None

    try:
        from google.genai import types
    except ImportError:
        print("[image] google-genai 미설치 - 이미지 생성 건너뜀", file=sys.stderr)
        return None

    contents: list = []
    if ref_image and ref_image.exists():
        contents.append(
            types.Part.from_bytes(data=ref_image.read_bytes(), mime_type="image/jpeg")
        )
    contents.append(prompt)

    # 이미지 모델은 기본이 이미지 응답이지만, 일부는 response_modalities 명시가 필요하다.
    configs = [
        None,
        types.GenerateContentConfig(response_modalities=["IMAGE"]),
        types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
    ]

    for selection in selections:
        backend = selection[0]
        try:
            client = make_client(selection)
        except Exception as exc:  # 클라이언트 생성 실패는 다음 백엔드로.
            print(f"[image] {backend} 클라이언트 실패({exc})", file=sys.stderr)
            continue
        for config in configs:
            try:
                kwargs = {"model": model, "contents": contents}
                if config is not None:
                    kwargs["config"] = config
                response = client.models.generate_content(**kwargs)
            except Exception as exc:
                print(f"[image] {backend} 호출 실패({exc})", file=sys.stderr)
                continue
            data = _extract_image_bytes(response)
            if data:
                print(f"[image] 생성 성공 ({backend}, {len(data)}B)", file=sys.stderr)
                return data
    print("[image] 모든 백엔드/모달리티 실패", file=sys.stderr)
    return None


# 숏폼 플랫폼 UI(상단 사용자명/시간, 하단 캡션/버튼)가 몰리는 세로 비율 밴드.
# 캡처 프레임을 카탈로그 참조로 넘기기 전에 이 영역을 잘라 UI 잔재 복제를 막는다.
UI_CROP_TOP = 0.11
UI_CROP_BOTTOM = 0.14


def capture_frame(video: Path, t_sec: float, out: Path) -> bool:
    """ffmpeg로 t_sec 지점의 한 프레임을 JPEG로 저장하고 상·하단 UI 밴드를 잘라낸다."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-ss", f"{max(t_sec, 0.0):.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        print(f"[frame] 캡처 실패 t={t_sec}: {proc.stderr[-300:]}", file=sys.stderr)
        return False

    try:
        from PIL import Image

        with Image.open(out) as img:
            w, h = img.size
            top = int(h * UI_CROP_TOP)
            bottom = int(h * (1.0 - UI_CROP_BOTTOM))
            if bottom > top:
                img.crop((0, top, w, bottom)).save(out, quality=92)
    except Exception as exc:  # 크롭 실패는 원본 프레임으로 진행.
        print(f"[frame] UI 크롭 생략({exc})", file=sys.stderr)
    return True


# --- 이미지 프롬프트 빌더 ------------------------------------------------------


def _product_prompt(ext: AssetExtraction) -> str:
    name = ext.product_name or "the product"
    packaging = ext.product_packaging or "as shown in the reference frame"
    return (
        f"Studio e-commerce product catalog photo of {name}. Packaging: {packaging}. "
        "Match the product's exact shape, color and label to the reference frame, but "
        "IGNORE any on-screen UI, watermarks, usernames, captions, timestamps, app "
        "interface, or graphic overlays in the reference; reproduce only the physical "
        "product(s). Clean seamless off-white studio background, soft even studio "
        "lighting, single hero product centered, subtle reflection, sharp focus, high "
        "detail, no text overlay, no hands, no human, vertical 9:16 framing, "
        "photorealistic."
    )


def _character_prompt(ext: AssetExtraction) -> str:
    bits = [
        ext.character_look,
        f"{ext.character_age} {ext.character_gender}".strip(),
        ext.character_body,
        f"wearing {ext.character_wardrobe}" if ext.character_wardrobe else "",
    ]
    desc = ". ".join(b for b in bits if b)
    return (
        f"Photorealistic upper-body portrait of a fictional beauty content creator. "
        f"{desc}. Soft natural indoor lighting, clean neutral background, looking at "
        "the camera with a warm approachable expression, authentic UGC aesthetic, "
        "high skin detail, vertical 9:16 framing. Not a real or identifiable person."
    )


# --- ReelProfile 조립 ----------------------------------------------------------


def _meta_from_container(vp: VideoProfile) -> InputMeta:
    """container 수치를 InputMeta로 옮긴다. 가드레일에 안 맞으면 기본값으로 떨어진다."""
    duration = vp.container.duration_sec or 18.0
    duration = min(max(duration, 1.0), 60.0)
    fps = int(round(vp.container.fps)) if vp.container.fps else 30
    if fps not in {24, 25, 30, 50, 60}:
        fps = 30

    width, height = 1080, 1920
    res = vp.container.resolution or ""
    if "x" in res:
        try:
            w, h = (int(x) for x in res.lower().split("x", 1))
            # 9:16 유지 + 1080x1920 이하일 때만 채택, 아니면 기본값.
            if 0 < w <= 1080 and 0 < h <= 1920 and w * 16 == h * 9:
                width, height = w, h
        except ValueError:
            pass

    return InputMeta(
        duration_sec=round(duration, 2),
        aspect_ratio="9:16",
        width=width,
        height=height,
        fps=fps,
        platform="tiktok",
        language="en",
    )


def _hook_from(vp: VideoProfile, ext: AssetExtraction) -> HookCandidate:
    hook_type = ext.hook_type if ext.hook_type in HOOK_TYPES else "H2"
    window = vp.hook.window_sec or [0.0, 3.0]
    return HookCandidate(
        hook_type=hook_type,
        headline=vp.hook.headline,
        bottom_caption=vp.hook.bottom_caption,
        visual_direction=vp.hook.visual or "",
        window_sec=(float(window[0]), float(window[1] if len(window) > 1 else 3.0)),
        rationale=f"레퍼런스 0~3초 후크를 {HOOK_TYPES[hook_type]['label']}로 분류.",
    )


def build_reel_profile(
    vp: VideoProfile,
    ext: AssetExtraction,
    video: Path,
    product_image: str | None,
    product_prompt: str,
    character_image: str | None,
    character_prompt: str,
) -> ReelProfile:
    """VideoProfile + 추출 결과 + 생성 이미지 경로를 ReelProfile(핵심만)로 합친다."""
    meta = _meta_from_container(vp)

    goal = _clean(ext.objective_goal) or (
        f"Promote {_clean(ext.product_name) or 'the product'} with a short-form vertical clip."
    )
    objective = Objective(
        goal=goal,
        video_type=_clean(ext.objective_video_type),
        target_audience=_clean(ext.objective_target_audience),
        key_message=_clean(ext.objective_key_message),
    )

    product = ProductSpec(
        name=_clean(ext.product_name) or _clean(vp.hook.product_line) or "Unknown product",
        usp=_clean(ext.product_usp),
        spec=_clean(ext.product_spec),
        packaging_desc=_clean(ext.product_packaging),
        affordances=ext.product_affordances,
    )

    character = ModelSpec(
        name=_clean(ext.character_name),
        age=_clean(ext.character_age),
        gender=_clean(ext.character_gender),
        look=_clean(ext.character_look),
        body=_clean(ext.character_body),
        wardrobe=_clean(ext.character_wardrobe),
    )

    cut = vp.cut
    cut_rhythm = CutRhythm(
        basis="beat_sync" if cut.sync == "beat_based" else "semantic_action",
        pattern=(
            f"{cut.count} cuts, mean {cut.mean_sec}s "
            f"(min {cut.min_sec}s / max {cut.max_sec}s), {cut.mode}"
        ),
        source="reference",
    )
    style = StyleDimensions(
        tone=vp.tone,
        pacing=cut.mode,
        cut_rhythm=cut_rhythm,
        hook=_hook_from(vp, ext),
        subtitle=SubtitleSpec(
            style=vp.subtitle.font_style,
            position=vp.subtitle.position,
            density=vp.subtitle.density,
        ),
        palette=vp.visual.palette,
        realism="hyper_realistic",
    )

    asset_bible = AssetBible(
        character=CharacterProfile(
            name=_clean(ext.character_name),
            prompt_used=character_prompt,
            key_shot_image=character_image,
        ),
        product=ProductProfile(
            name=_clean(ext.product_name),
            prompt_used=product_prompt,
            hero_image=product_image,
        ),
        environment=EnvironmentSpec(
            location=_clean(ext.environment_location),
            setting=_clean(ext.environment_setting),
            lighting=_clean(ext.environment_lighting),
            mood=_clean(ext.environment_mood),
            needs_image=False,
        ),
    )

    bpm = vp.music.bpm
    music = MusicSpec(
        mood=vp.tone[0] if vp.tone else None,
        dynamics=vp.music.dynamics,
        tempo=f"{int(bpm)} bpm" if bpm else None,
    )

    narration = NarrationSpec(
        delivery="voiceover" if vp.voice.present else "none",
        language="en",
        voice=VoiceSpec(
            enabled=vp.voice.present,
            type=vp.voice.tone,
            from_character=True,
        ),
    )

    provenance = Provenance(
        style_source="reference",
        reference_ref=str(video.name),
        text_model=resolve_model(None),
        seeds={
            "cut_count": cut.count,
            "cut_mean_sec": cut.mean_sec,
            "cut_mode": cut.mode,
            "bpm": bpm,
        },
    )

    return ReelProfile(
        meta=meta,
        objective=objective,
        product=product,
        character=character,
        style=style,
        narrative_arc=vp.narrative_arc,
        asset_bible=asset_bible,
        storyboard=Storyboard(),  # 핵심만: 스토리보드는 비움
        narration=narration,
        music=music,
        provenance=provenance,
    )


# --- 한 편 처리 ----------------------------------------------------------------


def process(video: Path, out_name: str, image_model: str) -> None:
    if not video.exists():
        print(f"[skip] 영상 없음: {video}", file=sys.stderr)
        return

    out_dir = OUT_ROOT / out_name
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== {video.name} -> {out_dir} ===", file=sys.stderr)

    # 1) 분석
    print("[1/4] 분석(analyze_video)...", file=sys.stderr)
    vp = analyze_video(str(video), url=f"official_{out_name}", use_gemini=True)

    # 2) 에셋 추출 (Gemini 멀티모달 1콜)
    print("[2/4] 에셋 추출(Gemini)...", file=sys.stderr)
    ext = run_multimodal(
        str(video),
        vp.container.duration_sec,
        AssetExtraction,
        _EXTRACT_PROMPT,
        _EXTRACT_PROMPT,
        log_prefix="extract",
    )
    if ext is None:
        print("[2/4] 추출 실패 - VideoProfile 값으로 최소 조립", file=sys.stderr)
        ext = AssetExtraction(
            product_name=vp.hook.product_line or "",
            product_packaging=vp.hook.visual or "",
            character_present=vp.voice.present,
        )

    # 3) 제품 카탈로그 이미지 (프레임 캡처 -> 나노바나나)
    print("[3/4] 제품 카탈로그 이미지...", file=sys.stderr)
    product_image_name: str | None = None
    product_prompt = _product_prompt(ext)
    duration = vp.container.duration_sec or 0.0
    t = ext.product_best_timestamp_sec
    if duration:
        t = min(max(t, 0.0), max(duration - 0.1, 0.0))
    frame_path = out_dir / "product-frame.jpg"
    if capture_frame(video, t, frame_path):
        data = generate_image(product_prompt, frame_path, image_model)
        if data:
            (out_dir / "product-catalog.jpg").write_bytes(data)
            product_image_name = "product-catalog.jpg"

    # 4) 캐릭터 이미지 (텍스트 -> 나노바나나)
    print("[4/4] 캐릭터 이미지...", file=sys.stderr)
    character_image_name: str | None = None
    character_prompt = _character_prompt(ext)
    if ext.character_present:
        data = generate_image(character_prompt, None, image_model)
        if data:
            (out_dir / "character.jpg").write_bytes(data)
            character_image_name = "character.jpg"

    # 5) ReelProfile 조립 + 저장
    profile = build_reel_profile(
        vp,
        ext,
        video,
        product_image_name,
        product_prompt,
        character_image_name,
        character_prompt,
    )
    out_json = out_dir / "ReelProfile.json"
    out_json.write_text(
        profile.model_dump_json(indent=2, exclude_none=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"[done] {out_json}  (product={product_image_name}, character={character_image_name})",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="레퍼런스 영상을 ReelProfile(핵심만) + 생성 에셋 이미지로 환원한다."
    )
    parser.add_argument("videos", nargs="+", help="환원할 영상 파일 경로(1개 이상)")
    parser.add_argument(
        "--out-name",
        action="append",
        default=None,
        help="영상별 출력 폴더명. 미지정 시 파일 이름에서 자동 생성.",
    )
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env", override=False)
    image_model = os.environ.get("GEMINI_IMAGE_MODEL") or DEFAULT_IMAGE_MODEL
    print(f"이미지 모델: {image_model}", file=sys.stderr)
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    for idx, raw in enumerate(args.videos):
        video = Path(raw)
        if args.out_name and idx < len(args.out_name):
            name = args.out_name[idx]
        else:
            name = _slug(video.stem)
        process(video, name, image_model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
