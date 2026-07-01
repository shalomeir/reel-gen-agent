"""ReelProfile + ProductionPlan -> Materials.

영상은 켄 번스(스켈레톤)/영상 백엔드(Milestone 2)로, 자막은 pilmoji로, BGM은 컷 주기에
bpm을 맞춰 만든다. voice는 voiceover일 때만 별도 생성(on_camera는 영상 모델이 품는다).
실제 Lyria/ElevenLabs는 키가 있을 때 쓰고, 없으면 BGM은 합성 베드로 무음을 피한다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .audio import bpm_for_cuts, compose_aligned_narration, synth_music_bed
from .backends.ken_burns import DEFAULT_MOTION, KenBurnsBackend
from .schema import Materials, ProductionPlan, ReelProfile
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


def _veo_prompt(base_prompt: str, motion: str) -> str:
    """패널 프롬프트에 컷 모션 카메라 지시문을 덧붙인다(영상 모델이 실제로 줌하도록)."""
    directive = _MOTION_DIRECTIVE.get(motion)
    if not directive:
        return base_prompt
    return f"{base_prompt}. Camera: {directive}." if base_prompt else directive


def _music_bpm(tempo: str | None) -> int | None:
    """MusicSpec.tempo 문자열("136 bpm")에서 bpm 정수를 뽑는다. 없으면 None."""
    if not tempo:
        return None
    m = re.search(r"(\d{2,3})", tempo)
    return int(m.group(1)) if m else None


def build_materials(profile: ReelProfile, plan: ProductionPlan, out_dir: str) -> Materials:
    panels_dir = Path(out_dir) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    m = profile.meta
    ken = KenBurnsBackend()
    veo = _video_backend(plan)  # Veo(있으면) / None. 실패 시 패널별 켄 번스로 폴백.
    clips: list[str] = []
    subs: list[str] = []
    total_dur = 0.0
    for i, panel in enumerate(profile.storyboard.panels):
        # 스틸이 없는 패널은 워킹 스켈레톤에서 만들 거리가 없으므로 건너뛴다.
        if not panel.still_image:
            continue
        dur = max(0.5, (panel.t_end or 0.0) - (panel.t_start or 0.0))
        clip = str(panels_dir / f"clip_{panel.index}.mp4")
        # plan.panel_motions는 패널 순서대로라 위치 i로 맞춘다(없으면 기본 모션).
        motion = plan.panel_motions[i] if i < len(plan.panel_motions) else DEFAULT_MOTION
        made = False
        if veo is not None:
            try:
                base = panel.prompt or profile.storyboard.global_prompt or ""
                veo.render_panel(
                    panel.still_image,
                    dur,
                    m.width,
                    m.height,
                    m.fps,
                    clip,
                    motion=motion,
                    prompt=_veo_prompt(base, motion),
                )
                made = True
            except Exception:
                made = False  # Veo 실패 -> 이 컷은 켄 번스로 폴백
        if not made:
            ken.render_panel(panel.still_image, dur, m.width, m.height, m.fps, clip, motion=motion)
        clips.append(clip)
        total_dur += dur
        sub = str(panels_dir / f"sub_{panel.index}.png")
        render_subtitle_png(panel.subtitle_text or "", m.width, m.height, sub)
        subs.append(sub)

    bgm_audio: str | None = None
    if plan.bgm != "none" and total_dur > 0:
        # BGM bpm: MusicSpec.tempo(예: 레퍼런스 "136 bpm")가 있으면 우선, 없으면 컷 주기로 산정.
        bpm = _music_bpm(profile.music.tempo) or bpm_for_cuts(profile.storyboard.panels)
        bgm_audio = _build_bgm(profile, plan, bpm, total_dur, str(panels_dir))

    # voice: 나레이션(voiceover)이면 비트별 대사를 각 패널 t_start에 정렬 배치해 합성한다.
    voice_audio = _build_voice(profile, str(panels_dir), total_dur)

    return Materials(
        shot_clips=clips, subtitle_pngs=subs, bgm_audio=bgm_audio, voice_audio=voice_audio
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
