"""ReelProfile + ProductionPlan -> Materials.

영상은 켄 번스(스켈레톤)/영상 백엔드로, 자막은 pilmoji로 만든다. 오디오는 세 갈래로 나뉘어
각각 필요할 때만 생성된다: voice(나레이션, voiceover일 때), bgm(음악 베드, plan.bgm!=none),
sfx(프로덕션 효과음, plan.sfx일 때). execute 그래프는 이 셋을 병렬 노드로 돌려 assemble에서
합친다. build_materials는 그 셋을 순차로 조합하는 얇은 헬퍼(단독 호출·테스트용)다.
실제 Lyria/ElevenLabs는 키가 있을 때 쓰고, 없으면 BGM은 합성 베드로 무음을 피한다.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .audio import bpm_for_cuts, compose_aligned_narration, synth_music_bed
from .backends.ken_burns import DEFAULT_MOTION, KenBurnsBackend
from .schema import Materials, ProductionPlan, ReelProfile, StoryboardPanel
from .subtitles import render_subtitle_png


@dataclass
class VisualMaterials:
    """영상 파트(오디오 제외). 병렬 오디오 노드가 total_dur를 공유해 트랙을 만든다."""

    shot_clips: list[str] = field(default_factory=list)
    subtitle_pngs: list[str] = field(default_factory=list)
    subtitle_spans: list[list[float]] = field(default_factory=list)
    total_dur: float = 0.0
    native_audio: bool = False  # 온카메라 발화(영상 네이티브 음성) 보존 여부


def _build_bgm(profile, plan, bpm: int, total_dur: float, panels_dir: str) -> str | None:
    """BGM을 만든다. plan.bgm=="gen"이면 1차 Lyria, 실패/그 외엔 합성 베드.

    빠른 반복이 필요하면 `REEL_BGM=synth`로 Lyria를 끄고 합성 베드만 쓴다.
    """
    # BGM 프롬프트는 음악 노드가 정한 MusicSpec에서만 만든다(스타일 하드코딩 금지). 비면
    # 장르 없는 중립 지시만 둔다(장르 선택은 코드가 아니라 LLM 음악 노드의 몫이다).
    style_bits = [profile.music.style, profile.music.mood, profile.music.type]
    prompt = ", ".join(b for b in style_bits if b) or "instrumental background music"
    use_lyria = (
        plan.bgm == "gen"
        and os.environ.get("REEL_BGM", "").lower() != "synth"
        and os.environ.get("GOOGLE_CLOUD_PROJECT")
    )
    if use_lyria:
        try:
            from .backends.lyria import LyriaMusicClient

            return LyriaMusicClient().generate(
                prompt, bpm, total_dur, str(Path(panels_dir) / "bgm.wav")
            )
        except Exception:
            pass  # Lyria 실패 -> 합성 베드 폴백
    return synth_music_bed(total_dur, bpm, str(Path(panels_dir) / "bgm.wav"))


def _video_backend(plan: ProductionPlan):
    """plan.video_model에 맞는 영상 백엔드. ken_burns/무설정이거나 REEL_VIDEO=ken_burns면 None.

    None이면 build_materials가 켄 번스 폴백만 쓴다. Veo는 생성이 비싸고 느리므로,
    빠른 반복이 필요하면 `REEL_VIDEO=ken_burns`로 강제로 끌 수 있다.
    """
    model = (plan.video_model or "ken_burns").lower()
    if model == "ken_burns" or os.environ.get("REEL_VIDEO", "").lower() == "ken_burns":
        return None
    if model.startswith("veo"):
        try:
            from .backends.veo import VeoBackend

            return VeoBackend(plan.video_model)
        except Exception:
            return None
    # Kling 등 다른 백엔드는 아직 미배선 -> 켄 번스 폴백.
    return None


# Veo 폴백 서브컷에 쓰는 zoom-in 계열 회전(모두 줌 1.0에서 시작). 컷 경계에서 배율이
# 점프해 같은 스틸에서도 컷이 감지되도록 한다(rhythm 보존). zoom_out은 경계 연속이라 제외.
_FALLBACK_MOTIONS = ("zoom_in_slow", "push_in", "product_push_in")


# 켄 번스 모션명 -> 영상 모델(Veo/Kling)에 넣을 카메라 무빙 지시문. 컷마다 카메라를
# 다르게 움직여야 컷 변화가 살고, 제품 컷은 제품으로 밀고 들어가야 강조가 된다.
_MOTION_DIRECTIVE: dict[str, str] = {
    "push_in": "slow cinematic push-in, camera drifts closer",
    "product_push_in": "slow push-in zooming into the product, product stays sharp and centered",
    "zoom_in_slow": "very slow, subtle zoom-in",
    "zoom_out_slow": "very slow, subtle zoom-out revealing more of the scene",
    "static": "locked-off static shot, no camera movement",
}


def _shot_subject(panel: StoryboardPanel, product_name: str) -> str:
    """이 컷의 피사체 한 줄. 제품 강조 컷이면 제품, 아니면 인물 중심."""
    if panel.product_lock:
        return f"the {product_name} product in focus" if product_name else "the product in focus"
    return "the beauty creator"


# beat -> 화면 동작 묘사. beat "라벨 단어"(problem/cta 등)를 프롬프트에 그대로 넣으면 영상
# 모델이 그 단어를 화면 자막으로 렌더해버린다. 그래서 라벨 대신 동작 문구로만 유도한다.
_BEAT_ACTION: dict[str, str] = {
    "hook": "an eye-catching opening beauty moment, engaging expression",
    "problem": "thoughtfully checking her skin",
    "discovery": "presenting the product to the camera",
    "reveal": "presenting the product to the camera",
    "use": "gently applying the product to her face",
    "apply": "gently applying the product to her face",
    "routine": "doing her skincare routine",
    "reaction": "a delighted, pleased reaction",
    "proof": "showing fresh, healthy-looking results with a happy expression",
    "after": "showing fresh, healthy-looking results with a happy expression",
    "result": "showing fresh, healthy-looking results with a happy expression",
    "benefit": "showing fresh, healthy-looking results with a happy expression",
    "demo": "demonstrating the product in use",
    "cta": "smiling warmly and invitingly at the camera",
}


def _beat_action(beat: str) -> str:
    """beat를 화면 동작 문구로 바꾼다(라벨 단어는 넣지 않는다)."""
    return _BEAT_ACTION.get(beat, "a natural beauty b-roll moment")


def _speech_directive(speaking: bool) -> str:
    """발화 지시문([ADR.md] ADR-0012). 나레이션(기본)이면 영상에서 말하는 느낌을 없애 립싱크
    불일치를 막고, 온카메라 발화가 필요할 때만 영상 모델이 립싱크로 직접 말하게 한다.
    """
    if speaking:
        return "The person speaks to the camera with natural, realistic lip-sync."
    return (
        "The person is NOT talking: mouth relaxed and mostly closed, no lip movement, no speaking, "
        "no lip-sync (voiceover is added separately)."
    )


# 피부 질감 지시문. 백엔드마다 광택을 다루는 성향이 달라 분기한다.
# - 기본(Kling 등): 자연스러운 피부 질감 요청(그대로 유지).
# - Veo: 피부 광택을 과장하는 경향이 있어 더 강하게 무광·비유광으로 억제한다(피부 부분만).
_SKIN_DIRECTIVE_BASE = (
    "Natural realistic skin texture with visible pores; avoid excessive dewy sheen, greasy "
    "highlights or plastic glossy skin."
)
_SKIN_DIRECTIVE_VEO = (
    "Skin must look matte and natural with realistic pores and texture; strongly avoid any wet, "
    "oily, dewy or glossy sheen, shiny highlights, greasy or plastic-looking skin. Keep the skin "
    "finish understated, not shiny and not glowing."
)


def _skin_directive(video_model: str | None) -> str:
    """영상 백엔드별 피부 지시문. Veo만 광택을 더 세게 억제한다(사용자 지시)."""
    if (video_model or "").lower().startswith("veo"):
        return _SKIN_DIRECTIVE_VEO
    return _SKIN_DIRECTIVE_BASE


def _multishot_prompt(
    seg_panels: list[StoryboardPanel],
    motions: list[str],
    product_name: str,
    style: str,
    speaking: bool,
    skin_directive: str,
    hook_visual: str = "",
    pacing: str | None = None,
    motion: str | None = None,
    product_identity: str = "",
) -> str:
    """세그먼트 안 패널들을 샷 리스트 멀티샷 프롬프트로 편다([multishot-segments.md]).

    앵커 이미지 1장 + 이 프롬프트로 영상 모델이 세그먼트 내부의 여러 컷을 스스로 만든다.
    컷마다 shot_type, 피사체(제품 컷은 제품), beat 동작, 카메라 무빙(제품 컷은 제품 줌인)을
    담아 컷 변화를 유도한다. 편집 결(hard/fast vs gentle/slow)은 pacing에서 유도해, 레퍼런스가
    느린 시연이면 컷이 하드하게 튀지 않게 한다(하드코딩 금지). 인물·제품 일관, 피부 질감,
    발화 여부(립싱크)를 명시적으로 요구한다.
    """
    from .pacing import edit_directive, motion_directive

    lines = [
        f"A single vertical 9:16 clip that moves through {len(seg_panels)} shots played one after "
        f"another over time ({edit_directive(pacing)}).",
    ]
    motion_feel = motion_directive(motion)
    if motion_feel:
        lines.append(motion_feel)
    # 제품은 시각 정체성으로 못박아 컷마다 모양·용기·색이 그대로 유지되게 한다(제품 흔들림 방지).
    product_line = (
        f"Keep the SAME product identical in every shot — the product is: {product_identity}. "
        "Its shape, packaging and colors must stay exactly the same across all shots."
        if product_identity
        else "Keep the same person and the same product consistent across every shot."
    )
    lines += [
        product_line,
        "Keep the same person consistent across every shot.",
        # Veo가 인물을 지나치게 사실적으로 바꾸며 매력도를 떨어뜨릴 때가 있어, 시작 이미지의
        # 미모·매력을 그대로 유지하라고 명시한다(단, 플라스틱 아닌 자연스러움은 유지).
        "Keep the person exactly as attractive and beautiful as the start image — flattering, "
        "photogenic, camera-ready; do not make her look plainer or less attractive.",
        skin_directive,
        _speech_directive(speaking),
        # 자막은 편집단계에서 따로 올리므로, 영상 모델이 화면에 글자를 그리면 안 된다.
        "Do not render any on-screen text, captions, subtitles, letters, words or watermarks; "
        "clean footage with no text overlay.",
    ]
    if style:
        lines.append(style)
    for k, panel in enumerate(seg_panels):
        shot = (panel.shot_type or "medium shot").strip()
        beat = (panel.beat or "").strip()
        # 컷의 의미 있는 행동은 스토리보드 노드가 정한 panel.action을 우선한다(멀뚱한 포즈 방지).
        # 훅 컷은 훅 시각 컨셉을, 둘 다 없으면 beat 기본 동작으로 폴백한다.
        action = (panel.action or "").strip()
        if beat == "hook" and hook_visual:
            action = hook_visual
        if not action:
            action = _beat_action(beat)
        directive = _MOTION_DIRECTIVE.get(motions[k], "")
        cam = (panel.camera or "").strip()
        cam_bit = f". Camera: {cam or directive}" if (cam or directive) else ""
        subject = _shot_subject(panel, product_name)
        lines.append(f"Shot {k + 1}: {shot} — {subject}, {action}{cam_bit}.")
    return "\n".join(lines)


def _last_frame(clip: str, out_png: str) -> str | None:
    """클립의 마지막 프레임을 PNG로 뽑는다(다음 세그먼트 start image 연결용)."""
    cmd = [
        "ffmpeg", "-y", "-sseof", "-0.3", "-i", clip,
        "-update", "1", "-frames:v", "1", out_png,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        return None
    return out_png if Path(out_png).exists() else None


def _music_bpm(tempo: str | None) -> int | None:
    """MusicSpec.tempo 문자열("136 bpm")에서 bpm 정수를 뽑는다. 없으면 None."""
    if not tempo:
        return None
    m = re.search(r"(\d{2,3})", tempo)
    return int(m.group(1)) if m else None


def _panel_dur(panel: StoryboardPanel) -> float:
    return max(0.5, (panel.t_end or 0.0) - (panel.t_start or 0.0))


# 서브컷 프레이밍은 스토리보드가 정한 shot_type(macro/CU/medium/wide)에서 나온다. 줌 배율만
# 아니라 세로 크롭 앵커(제품 컷은 아래=손/제품, 인물 컷은 위=얼굴)까지 달리해, 연속 Veo
# 푸티지에서 잘라낸 인접 서브컷의 프레임이 확 달라지도록 한다(컷 감지기가 경계를 안정적으로
# 잡음 = fast_montage 컷 리듬 복원). 하드코딩 매직넘버가 아니라 계획된 샷 다양성의 렌더링이다.
_SHOT_ZOOM = [
    (("macro", "extreme", "ecu"), 1.4),
    (("close", "cu"), 1.22),
    (("medium",), 1.08),
    (("wide", "full", "establish", "over"), 1.0),
]


def _beat_cut_frame(panel: StoryboardPanel, cut_index: int) -> tuple[float, float]:
    """(줌, 세로 크롭 중심 0~1)을 shot_type + 제품 여부로 정한다.

    shot_type이 큰 줌을 요구하면(macro/CU) 크게, wide면 원본에 가깝게. 세로 앵커는 제품 컷이면
    아래쪽(손·제품), 인물 컷이면 위쪽(얼굴)을 잡아 인접 컷의 화면 영역이 크게 달라지게 한다.
    shot_type 단서가 없으면 컷 순번 홀짝으로 줌을 번갈아 폴백한다.
    """
    st = (panel.shot_type or "").lower()
    zoom = next((z for keys, z in _SHOT_ZOOM if any(k in st for k in keys)), None)
    if zoom is None:
        zoom = 1.0 if cut_index % 2 == 0 else 1.22
    if panel.product_lock:
        zoom = max(zoom, 1.2)  # 제품 강조는 최소한 밀어 넣는다
    y_frac = 0.62 if panel.product_lock else 0.42  # 제품=아래(손/제품), 인물=위(얼굴)
    return round(zoom, 3), y_frac


def _extract_subcut(
    seg_clip: str, start: float, dur: float, zoom: float, w: int, h: int, fps: int, out: str,
    keep_audio: bool = False, y_frac: float = 0.5,
) -> str:
    """세그먼트 클립의 [start, start+dur] 구간을 줌·세로앵커 프레이밍으로 잘라 서브컷을 만든다.

    입력 영상(Veo)은 이미 움직이므로 정지 위험이 없다. 컷마다 zoom과 세로 크롭 위치를 달리해
    인접 서브컷의 경계 프레임이 확 달라지면 컷 감지기가 경계를 잡아 fast_montage 리듬이 산다.
    온카메라 발화(integrated)면 연속 시간 슬라이스라 네이티브 음성을 보존한다.
    """
    # 중앙 x, 세로는 y_frac 위치. zoom=1.0이면 오프셋 0(원본 프레임).
    y_expr = f"(ih*{zoom}-{h})*{y_frac:.3f}"
    vf = f"scale=iw*{zoom}:ih*{zoom},crop={w}:{h}:(iw*{zoom}-{w})/2:{y_expr},setsar=1"
    cmd = [
        "ffmpeg", "-y", "-i", seg_clip, "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
        "-vf", vf, "-r", str(fps),
    ]
    cmd += (["-c:a", "aac"] if keep_audio else ["-an"])
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", out]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def build_visuals(
    profile: ReelProfile,
    plan: ProductionPlan,
    out_dir: str,
    image_client=None,
    character_image: str | None = None,
    product_image: str | None = None,
    key_visual: str | None = None,
) -> VisualMaterials:
    """세그먼트 단위로 영상 클립+자막을 만든다([multishot-segments.md]). 오디오는 만들지 않는다.

    영상 백엔드가 있으면 세그먼트당 1회 호출(앵커 이미지 1장 + 멀티샷 프롬프트, 2번째부터는
    직전 세그먼트 마지막 프레임으로 연결)로 만든다. 영상 모델이 실패하면(예: Veo RAI/장애)
    그 세그먼트는 켄 번스 폴백으로 내려가는데, image_client가 있으면 컷마다 개별 스틸을
    생성해(없는 것만) 서로 다른 이미지로 진짜 몽타주를 유지한다 -> 영상 모델이 죽어도 컷
    리듬(rhythm)이 무너지지 않는다. Veo가 성공한 세그먼트엔 개별 스틸을 만들지 않는다(비용 0).
    자막은 패널별 PNG를 최종 타임라인 구간에 시간 기반으로 덮는다. total_dur를 함께 돌려주어
    병렬 오디오 노드(voice/bgm/sfx)가 트랙 길이를 맞추게 한다.
    """
    panels_dir = Path(out_dir) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    m = profile.meta
    panels = profile.storyboard.panels
    ken = KenBurnsBackend()
    veo = _video_backend(plan)  # Veo(있으면) / None. 실패 시 앵커 스틸 켄 번스로 폴백.
    # segments가 없으면(직접 만든 plan) 패널당 1개로 둔다.
    segments = plan.segments or [[i] for i in range(len(panels))]
    product_name = profile.product.name or ""
    from .product import product_identity

    product_id = product_identity(profile.product)  # 컷마다 제품을 고정할 시각 정체성
    style = profile.storyboard.global_prompt or ""
    # 온카메라 발화(integrated)일 때만 영상 모델이 립싱크로 말하고 음성도 직접 낸다. 기본
    # 나레이션(separate_tts/none)은 영상에서 말하는 느낌을 없애 립싱크 불일치를 막는다.
    speaking = plan.voice_strategy == "integrated"
    # 영상 모델은 씬 오디오(효과음/앰비언스)를 거의 항상 생성한다(무음 영상 지양, plan이 결정).
    # integrated는 발화까지 네이티브로 내야 하므로 항상 오디오 on. 발화 여부는 speech 지시가 가른다
    # (voiceover면 "말하지 않음"으로 씬 사운드만, integrated면 립싱크 발화까지).
    gen_audio = bool(plan.video_native_audio) or speaking
    skin_directive = _skin_directive(plan.video_model)  # Veo만 피부 광택을 더 세게 억제
    # 생성된 훅의 시각 컨셉을 훅 컷 생성에 반영한다(첫 3초가 훅을 실현하도록).
    hook_visual = (profile.style.hook.visual_direction or "") if profile.style.hook else ""

    clips: list[str] = []
    subs: list[str] = []
    spans: list[list[float]] = []
    total_dur = 0.0
    prev_last_frame: str | None = None
    cut_index = 0  # 전체 서브컷 순번(줌 홀짝 번갈기용)
    made_any = False  # Veo가 오디오 있는 클립을 하나라도 만들었나(씬 오디오 보존 판단)

    for seg_pos, indices in enumerate(segments):
        anchor = panels[indices[0]]
        if not anchor.still_image:
            continue  # 앵커 스틸이 없으면 만들 거리가 없다.
        seg_dur = sum(_panel_dur(panels[i]) for i in indices)
        motions = [
            plan.panel_motions[i] if i < len(plan.panel_motions) else DEFAULT_MOTION
            for i in indices
        ]
        seg_clip = str(panels_dir / f"clip_{seg_pos}.mp4")

        made = False
        if veo is not None:
            try:
                start_image = prev_last_frame or anchor.still_image
                prompt = _multishot_prompt(
                    [panels[i] for i in indices], motions, product_name, style, speaking,
                    skin_directive, hook_visual, pacing=profile.style.pacing,
                    motion=profile.style.motion, product_identity=product_id,
                )
                veo.render_panel(
                    start_image, seg_dur, m.width, m.height, m.fps, seg_clip,
                    motion=motions[0], prompt=prompt, generate_audio=gen_audio,
                )
                made = True
                made_any = True
            except Exception as exc:
                # 영상 모델 실패 -> 앵커 스틸 폴백. 조용히 삼키지 않고 원인을 노출한다.
                made = False
                print(
                    f"[materials] Veo 세그먼트{seg_pos}(패널 {indices}) 실패 -> 스틸 폴백: {exc}",
                    file=sys.stderr,
                )
        # 폴백이면 이 세그먼트 패널들에 개별 스틸을 채운다(없는 것만). 컷마다 다른 이미지가
        # 있어야 컷 감지기가 경계를 잡아 rhythm이 보존된다(같은 스틸 줌 변주만으론 컷이 안 잡힌다).
        if not made and image_client is not None:
            try:
                from .stills import ensure_panel_stills

                ensure_panel_stills(
                    profile, out_dir, image_client, character_image, product_image,
                    anchor_indices=set(indices), key_visual=key_visual,
                )
            except Exception as exc:
                print(f"[materials] 폴백 패널 스틸 생성 실패(앵커로 진행): {exc}", file=sys.stderr)

        # 컷 단위 재분할. Veo 성공이면 실 영상 세그먼트를 패널 경계로 잘라 컷마다 줌을 달리한다.
        # Veo 실패(폴백)면 패널별 개별 스틸을 각자 ken_burns 서브컷으로 만들어 진짜 몽타주를
        # 유지한다(컷마다 다른 이미지 -> 컷 감지). 부드러운 줌이라 정지(not_frozen) 문제도 없다.
        local = 0.0
        for i in indices:
            p = panels[i]
            d = _panel_dur(p)
            sub_clip = str(panels_dir / f"clip_{seg_pos}_{i}.mp4")
            if made:
                zoom, y_frac = _beat_cut_frame(p, cut_index)
                _extract_subcut(
                    seg_clip, local, d, zoom, m.width, m.height, m.fps, sub_clip,
                    keep_audio=gen_audio, y_frac=y_frac,
                )
            else:
                # 폴백: 이 컷의 개별 스틸(없으면 앵커)을 zoom-in 계열 모션으로 렌더한다. 컷마다
                # 다른 이미지라 경계가 확실히 잡히고, 부드러운 줌으로 정지 문제도 없다.
                still_i = panels[i].still_image or anchor.still_image
                motion_i = _FALLBACK_MOTIONS[cut_index % len(_FALLBACK_MOTIONS)]
                ken.render_panel(
                    still_i, d, m.width, m.height, m.fps, sub_clip, motion=motion_i,
                )
            clips.append(sub_clip)
            cut_index += 1
            # 자막: 계획된 패널 구간에 시간 기반으로 건다(모델 내부 컷과 무관).
            if (p.subtitle_text or "").strip():
                sub = str(panels_dir / f"sub_{p.index}.png")
                render_subtitle_png(p.subtitle_text or "", m.width, m.height, sub)
                subs.append(sub)
                spans.append([total_dur + local, total_dur + local + d])
            local += d

        total_dur += seg_dur
        if veo is not None and made and seg_pos + 1 < len(segments):
            prev_last_frame = _last_frame(seg_clip, str(panels_dir / f"lastframe_{seg_pos}.png"))

    return VisualMaterials(
        shot_clips=clips,
        subtitle_pngs=subs,
        subtitle_spans=spans,
        total_dur=total_dur,
        # Veo가 오디오 있는 클립을 만들었으면 그 씬 오디오를 보존한다(integrated면 발화,
        # voiceover면 나레이션 아래 씬 효과음). ken_burns 폴백만 있으면 무음이라 False.
        native_audio=made_any and gen_audio,
    )


def build_bgm_track(
    profile: ReelProfile, plan: ProductionPlan, out_dir: str, total_dur: float
) -> tuple[str | None, float]:
    """BGM 트랙과 믹스 게인을 만든다(plan.bgm!=none일 때). 병렬 오디오 노드 중 하나.

    tempo는 MusicSpec.tempo(레퍼런스 bpm) 우선, 없으면 컷 주기로 숏폼 경쾌 대역에서 산정한다.
    게인은 music.prominence를 따른다(prominent면 크게, background도 또렷하게).
    """
    panels_dir = str(Path(out_dir) / "panels")
    bgm_audio: str | None = None
    if plan.bgm != "none" and total_dur > 0:
        bpm = _music_bpm(profile.music.tempo) or bpm_for_cuts(profile.storyboard.panels)
        bgm_audio = _build_bgm(profile, plan, bpm, total_dur, panels_dir)
    bgm_gain = 0.85 if (profile.music.prominence or "").lower() == "prominent" else 0.45
    return bgm_audio, bgm_gain


def build_voice_track(profile: ReelProfile, out_dir: str, total_dur: float) -> str | None:
    """나레이션(voiceover) voice 트랙을 만든다(delivery=voiceover + 대사 있을 때). 병렬 노드."""
    return _build_voice(profile, str(Path(out_dir) / "panels"), total_dur)


def build_sfx_track(
    profile: ReelProfile, plan: ProductionPlan, out_dir: str
) -> tuple[list[str], list[float]]:
    """프로덕션 효과음 트랙들을 만든다(plan.sfx일 때만, 보수적). 병렬 노드."""
    if not plan.sfx:
        return [], []
    return _build_sfx(profile, plan, str(Path(out_dir) / "panels"))


def build_materials(
    profile: ReelProfile,
    plan: ProductionPlan,
    out_dir: str,
    image_client=None,
    character_image: str | None = None,
    product_image: str | None = None,
) -> Materials:
    """영상 + 오디오 3종을 순차로 조합해 Materials를 만든다(단독 호출·테스트용 헬퍼).

    execute 그래프는 이 함수 대신 build_visuals + build_(bgm|voice|sfx)_track을 병렬 노드로
    돌리고 assemble에서 합친다. 결과물은 동일하다.
    """
    v = build_visuals(profile, plan, out_dir, image_client, character_image, product_image)
    bgm_audio, bgm_gain = build_bgm_track(profile, plan, out_dir, v.total_dur)
    voice_audio = build_voice_track(profile, out_dir, v.total_dur)
    sfx_audio, sfx_starts = build_sfx_track(profile, plan, out_dir)
    return Materials(
        shot_clips=v.shot_clips,
        subtitle_pngs=v.subtitle_pngs,
        subtitle_spans=v.subtitle_spans,
        bgm_audio=bgm_audio,
        voice_audio=voice_audio,
        sfx_audio=sfx_audio,
        sfx_starts=sfx_starts,
        native_audio=v.native_audio,
        bgm_gain=bgm_gain,
    )


# 한 편에 생성할 SFX 최대 개수. 비용·과밀을 막는 상한(넘는 컷 큐는 조용히 건너뛴다).
_MAX_SFX = 4


def _build_sfx(
    profile: ReelProfile, plan: ProductionPlan, panels_dir: str
) -> tuple[list[str], list[float]]:
    """컷별 sfx 큐가 있는 패널에 짧은 효과음을 생성해 (경로들, 시작초들)로 돌려준다.

    SFX 문구는 스토리보드가 준 panel.sfx(자연어 사운드 묘사)에서만 온다(하드코딩 금지). 각
    효과음은 그 컷 t_start에 놓이고 컷 길이만큼 생성한다. 키가 없거나 실패하면 그 컷은 건너뛴다.
    """
    if not os.environ.get("ELEVENLABS_API_KEY"):
        return [], []
    try:
        from .backends.sfx import ElevenLabsSfxClient

        client = ElevenLabsSfxClient()
    except Exception:
        return [], []
    paths: list[str] = []
    starts: list[float] = []
    for p in profile.storyboard.panels:
        cue = (p.sfx or "").strip()
        if not cue:
            continue
        out = str(Path(panels_dir) / f"sfx_{p.index}.mp3")
        try:
            client.generate(cue, _panel_dur(p), out)
        except Exception:
            continue  # 이 컷 SFX 실패 -> 건너뛴다(무음 아님, 나머지는 유지)
        paths.append(out)
        starts.append(max(0.0, p.t_start or 0.0))
        if len(paths) >= _MAX_SFX:
            break
    return paths, starts


def _tts_client(desc: str):
    """(text, out) -> path 콜러블. 호출마다 1차 ElevenLabs, 실패/무키면 Gemini TTS 폴백."""
    eleven = None
    if os.environ.get("ELEVENLABS_API_KEY"):
        try:
            from .backends.voice_tts import ElevenLabsVoiceClient

            eleven = ElevenLabsVoiceClient()
        except Exception:
            eleven = None

    def tts(text: str, out: str) -> str:
        if eleven is not None:
            try:
                return eleven.synthesize(text, desc, out)
            except Exception:
                pass  # ElevenLabs 실패 -> Gemini TTS 폴백
        from .backends.gemini_tts import GeminiTTSVoiceClient

        return GeminiTTSVoiceClient().synthesize(text, desc, out)

    return tts


def _build_voice(profile: ReelProfile, panels_dir: str, total_dur: float) -> str | None:
    """비트별 나레이션을 스토리보드 t_start에 맞춰 깔아 전체 길이 voice 트랙으로 만든다.

    delivery가 voiceover이고 대사가 있을 때만. 각 대사를 TTS(1차 ElevenLabs, 폴백 Gemini)한 뒤
    compose_aligned_narration이 패널 t_start에 배치·합성한다. 잘리지 않고 콘티에 맞물린다.
    """
    if profile.narration.delivery != "voiceover":
        return None
    lines = [line for line in profile.narration.lines if line.text.strip()]
    if not lines or total_dur <= 0:
        return None
    # voice 페르소나에 레퍼런스 발화의 결(tone/pace)을 실어 TTS 연기를 맞춘다(결정론 하드코딩 아님).
    voice = profile.narration.voice
    desc_bits = [voice.type or ""]
    if voice.tone:
        desc_bits.append(f"delivery tone: {voice.tone}")
    if voice.pace:
        desc_bits.append(f"pace: {voice.pace}")
    try:
        tts = _tts_client(" | ".join(b for b in desc_bits if b))
        return compose_aligned_narration(
            lines,
            profile.storyboard.panels,
            total_dur,
            tts,
            panels_dir,
            str(Path(panels_dir) / "voice.wav"),
        )
    except Exception:
        return None
