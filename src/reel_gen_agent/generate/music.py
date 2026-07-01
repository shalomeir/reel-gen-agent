"""음악(BGM) 정의 노드: 영상 목적·톤·제품·레퍼런스로 MusicSpec을 LLM이 정한다.

원칙(사용자 지시): "팝으로", "밝게" 같은 스타일 선택을 코드나 프롬프트에 하드코딩하지
않는다. 노드마다 LLM(Gemini/Claude)이 문맥에 맞는 음악(장르·무드·다이내믹)을 고른다.
레퍼런스가 있으면 그 음악 무드를 힌트로 반영한다. LLM이 없을 때만 최소한의 중립값을 쓴다.
"""

from __future__ import annotations

import json

from .schema import ModelSpec, MusicSpec, ProductSpec
from .text_client import TextClient

_PROMPT = (
    "You are a short-form music supervisor. Pick the MUSIC that makes this specific vertical beauty "
    "reel feel great, then the audio-effect flags. Short-form lives or dies on music you can FEEL — "
    "choose a characterful, engaging genre/mood with real energy; never a bland, generic, forgettable "
    "bed. Match the video's editing energy and tone: a fast/montage or transformation edit wants "
    "upbeat, driving, catchy music (it can be prominent and build to the payoff); a slow, sensorial "
    "edit wants a calmer but still tasteful, textured track. Do not default to any fixed genre — fit "
    "THIS video's flow.\n"
    "Brief: {brief}\nProduct: {product}\nTone: {tone}\nCreator: {character}\n"
    "Editing energy (cut pacing): {pacing}\n{ref}\n"
    'Output raw JSON only (no markdown, no prose): '
    '{{"style": str, "mood": str, "type": str, "dynamics": "flat"|"build", '
    '"prominence": "background"|"prominent", "vocal": bool, "bgm": "bed"|"none", "sfx": bool}}. '
    "style is the genre/production style; type is a short descriptor; dynamics is whether energy "
    "rises to a payoff (build) or stays even (flat). prominence: 'prominent' when the video is "
    "vibe/aesthetic-driven and narration is minimal/interjections (music should be felt loudly), "
    "else 'background' when narration carries the information. vocal: true if the track has "
    "singing/lyrics (e.g. a pop song) rather than a purely instrumental bed. bgm: 'none' only when "
    "the concept works better with NO music bed (e.g. crisp ASMR/texture-forward), otherwise 'bed'. "
    "sfx: true ONLY when the edit calls for produced, non-diegetic effect sounds — transition "
    "whooshes on cuts, graphic/sparkle accents, a hook riser, or an ending jingle/ding (a punchy, "
    "'variety-show' edited feel). Do NOT set sfx for natural in-scene sounds (spray, tap, pour) — "
    "the video model renders those. Default false unless the concept clearly wants that produced edit."
)


def _extract_json(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


def derive_music(
    brief: str,
    product: ProductSpec,
    tone: list[str],
    reference_music: MusicSpec | None,
    text_client: TextClient | None,
    character: ModelSpec | None = None,
    pacing: str | None = None,
) -> MusicSpec:
    """브리프·톤·페이싱·레퍼런스로 MusicSpec을 도출한다. LLM 우선, 실패/부재 시 레퍼런스/중립 폴백.

    영상의 편집 에너지(pacing)와 톤을 반영해 '체감되는' 장르/무드/에너지를 고른다(밋밋한 베드
    방지). tempo(bpm)는 컷 리듬과 맞춰야 하므로 여기서 정하지 않는다(execute가 컷 주기로 산정
    하거나 레퍼런스 bpm을 쓴다). 레퍼런스 tempo가 있으면 보존한다.
    """
    ref = reference_music or MusicSpec()
    ref_hint = ""
    if ref.mood or ref.style or ref.dynamics:
        # 레퍼런스는 무드/스타일 계열 힌트일 뿐, 에너지 상한이 아니다. 영상 흐름이 신나면 신나게.
        ref_hint = (
            f"Reference music (mood/style family hint only — do NOT let it cap the energy; the "
            f"video's flow decides energy): mood={ref.mood or 'unknown'}, "
            f"style={ref.style or 'unknown'}, dynamics={ref.dynamics or 'unknown'}."
        )

    if text_client is not None:
        try:
            from .character import character_brief

            raw = text_client.complete(
                _PROMPT.format(
                    brief=brief, product=product.name, tone=", ".join(tone) or "unspecified",
                    character=(character_brief(character) if character else "unspecified"),
                    pacing=pacing or "unspecified",
                    ref=ref_hint,
                ),
                temperature=0.7,
            )
            data = json.loads(_extract_json(raw))
            style = str(data.get("style") or "").strip() or ref.style
            mood = str(data.get("mood") or "").strip() or ref.mood
            type_ = str(data.get("type") or "").strip() or ref.type
            dynamics = str(data.get("dynamics") or "").strip() or ref.dynamics
            prominence = "prominent" if str(data.get("prominence", "")).strip().lower() == "prominent" else "background"
            vocal = bool(data.get("vocal", False))
            bgm = "none" if str(data.get("bgm", "")).strip().lower() == "none" else "bed"
            sfx = bool(data.get("sfx", False))
            # 보컬/가사가 있으면 배경으로 너무 묻지 않게 존재감을 올린다(사용자 지시).
            if vocal and prominence != "prominent":
                prominence = "prominent"
            if style or mood or type_:
                return MusicSpec(
                    mood=mood, style=style, type=type_, dynamics=dynamics, tempo=ref.tempo,
                    prominence=prominence, vocal=vocal, bgm=bgm, sfx=sfx,
                )
        except Exception:
            pass

    # LLM이 없거나 실패: 레퍼런스 음악을 그대로 쓰고, 그것도 없으면 톤 첫 단어를 무드로만 둔다.
    if ref.mood or ref.style or ref.dynamics or ref.tempo:
        return ref
    return MusicSpec(mood=(tone[0] if tone else None), tempo=ref.tempo)
