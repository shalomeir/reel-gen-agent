"""ReelProfile + ProductionPlan -> Materials.

영상은 켄 번스(스켈레톤)/영상 백엔드(Milestone 2)로, 자막은 pilmoji로, BGM은 컷 주기에
bpm을 맞춰 만든다. voice는 voiceover일 때만 별도 생성(on_camera는 영상 모델이 품는다).
실제 Lyria/ElevenLabs는 키가 있을 때 쓰고, 없으면 BGM은 합성 베드로 무음을 피한다.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .audio import bpm_for_cuts, compose_aligned_narration, synth_music_bed
from .backends.ken_burns import DEFAULT_MOTION, KenBurnsBackend
from .schema import Materials, ProductionPlan, ReelProfile, StoryboardPanel
from .subtitles import render_subtitle_png


def _build_bgm(profile, plan, bpm: int, total_dur: float, panels_dir: str) -> str | None:
    """BGM을 만든다. plan.bgm=="gen"이면 1차 Lyria, 실패/그 외엔 합성 베드.

    빠른 반복이 필요하면 `REEL_BGM=synth`로 Lyria를 끄고 합성 베드만 쓴다.
    """
    style_bits = [profile.music.style, profile.music.mood, profile.music.type]
    prompt = ", ".join(b for b in style_bits if b) or "bright upbeat pop for a beauty short"
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
) -> str:
    """세그먼트 안 패널들을 샷 리스트 멀티샷 프롬프트로 편다([multishot-segments.md]).

    앵커 이미지 1장 + 이 프롬프트로 영상 모델이 세그먼트 내부의 여러 컷을 스스로 만든다.
    컷마다 shot_type, 피사체(제품 컷은 제품), beat 동작, 카메라 무빙(제품 컷은 제품 줌인)을
    담아 컷 변화를 유도한다. 인물·제품 일관, 피부 질감, 발화 여부(립싱크)를 명시적으로 요구한다.
    """
    lines = [
        f"Multishot sequence of {len(seg_panels)} quick vertical 9:16 shots for a beauty short.",
        "Keep the same person and the same product consistent across every shot.",
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
        action = _beat_action((panel.beat or "").strip())
        directive = _MOTION_DIRECTIVE.get(motions[k], "")
        cam_bit = f". Camera: {directive}" if directive else ""
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


# 컷 인덱스 홀짝으로 줌 배율을 크게 번갈아, 연속 영상에서 잘라낸 인접 서브컷의 프레이밍이
# 확 달라져 컷 감지기가 경계를 잡게 한다(편집단계 beat-cut 몽타주, [multishot-segments.md]).
# 제품 강조 컷은 더 세게 밀어 제품으로 줌인한다.
_CUT_BASE_ZOOM = (1.0, 1.22)


def _beat_cut_zoom(cut_index: int, product_lock: bool) -> float:
    """서브컷의 줌 배율. 홀짝으로 크게 번갈고, 제품 컷은 추가로 밀어 넣는다."""
    z = _CUT_BASE_ZOOM[cut_index % 2]
    if product_lock:
        z += 0.10  # 제품 강조: 제품으로 더 크게 줌인
    return round(z, 3)


def _extract_subcut(
    seg_clip: str, start: float, dur: float, zoom: float, w: int, h: int, fps: int, out: str
) -> str:
    """세그먼트 클립의 [start, start+dur] 구간을 줌 프레이밍으로 잘라 서브컷을 만든다.

    입력 영상(Veo)은 이미 움직이므로 정지 위험이 없다. 컷마다 zoom을 달리해 중앙 punch-in을
    주면, 인접 서브컷의 경계 프레임이 확 달라져 fast_montage 컷 리듬이 살아난다.
    """
    vf = f"scale=iw*{zoom}:ih*{zoom},crop={w}:{h},setsar=1"
    cmd = [
        "ffmpeg", "-y", "-i", seg_clip, "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
        "-vf", vf, "-r", str(fps), "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", out,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def build_materials(profile: ReelProfile, plan: ProductionPlan, out_dir: str) -> Materials:
    """세그먼트 단위로 클립을 만든다([multishot-segments.md]).

    영상 백엔드가 있으면 세그먼트당 1회 호출(앵커 이미지 1장 + 멀티샷 프롬프트, 2번째부터는
    직전 세그먼트 마지막 프레임으로 연결)로 만든다. 없거나 실패하면 세그먼트 앵커 스틸을
    켄 번스 줌으로 대체한다. 자막은 패널별 PNG를 최종 타임라인 구간에 시간 기반으로 덮는다.
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
    style = profile.storyboard.global_prompt or ""
    # 온카메라 발화(integrated)일 때만 영상 모델이 립싱크로 말하고 음성도 직접 낸다. 기본
    # 나레이션(separate_tts/none)은 영상에서 말하는 느낌을 없애 립싱크 불일치를 막는다.
    speaking = plan.voice_strategy == "integrated"
    skin_directive = _skin_directive(plan.video_model)  # Veo만 피부 광택을 더 세게 억제

    clips: list[str] = []
    subs: list[str] = []
    spans: list[list[float]] = []
    total_dur = 0.0
    prev_last_frame: str | None = None
    cut_index = 0  # 전체 서브컷 순번(줌 홀짝 번갈기용)

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
                    skin_directive,
                )
                veo.render_panel(
                    start_image, seg_dur, m.width, m.height, m.fps, seg_clip,
                    motion=motions[0], prompt=prompt, generate_audio=speaking,
                )
                made = True
            except Exception:
                made = False  # 영상 모델 실패 -> 앵커 스틸 켄 번스로 폴백
        if not made:
            # 폴백: 세그먼트 앵커 스틸을 세그먼트 길이만큼 켄 번스 줌으로 렌더한다.
            ken.render_panel(
                anchor.still_image, seg_dur, m.width, m.height, m.fps, seg_clip, motion=motions[0]
            )

        # 편집단계 beat-cut 몽타주: 실 영상 세그먼트는 패널 경계로 재분할해 컷마다 줌을 달리한다.
        # 켄 번스 폴백은 이미 앵커 스틸 하나라 재분할하지 않는다(그대로 한 컷).
        local = 0.0
        for i in indices:
            p = panels[i]
            d = _panel_dur(p)
            if made:
                zoom = _beat_cut_zoom(cut_index, p.product_lock)
                sub_clip = str(panels_dir / f"clip_{seg_pos}_{i}.mp4")
                _extract_subcut(seg_clip, local, d, zoom, m.width, m.height, m.fps, sub_clip)
                clips.append(sub_clip)
                cut_index += 1
            # 자막: 계획된 패널 구간에 시간 기반으로 건다(모델 내부 컷과 무관).
            if (p.subtitle_text or "").strip():
                sub = str(panels_dir / f"sub_{p.index}.png")
                render_subtitle_png(p.subtitle_text or "", m.width, m.height, sub)
                subs.append(sub)
                spans.append([total_dur + local, total_dur + local + d])
            local += d
        if not made:
            clips.append(seg_clip)  # 폴백은 세그먼트 통째로 한 컷
            cut_index += 1

        total_dur += seg_dur
        if veo is not None and made and seg_pos + 1 < len(segments):
            prev_last_frame = _last_frame(seg_clip, str(panels_dir / f"lastframe_{seg_pos}.png"))

    bgm_audio: str | None = None
    if plan.bgm != "none" and total_dur > 0:
        # BGM bpm: MusicSpec.tempo(예: 레퍼런스 "136 bpm")가 있으면 우선, 없으면 컷 주기로 산정.
        bpm = _music_bpm(profile.music.tempo) or bpm_for_cuts(profile.storyboard.panels)
        bgm_audio = _build_bgm(profile, plan, bpm, total_dur, str(panels_dir))

    # voice: 나레이션(voiceover)이면 비트별 대사를 각 패널 t_start에 정렬 배치해 합성한다.
    voice_audio = _build_voice(profile, str(panels_dir), total_dur)

    return Materials(
        shot_clips=clips,
        subtitle_pngs=subs,
        subtitle_spans=spans,
        bgm_audio=bgm_audio,
        voice_audio=voice_audio,
    )


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
    try:
        tts = _tts_client(profile.narration.voice.type or "")
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
