"""음악(BGM) 정의 노드: 영상 목적·톤·제품·레퍼런스로 MusicSpec을 LLM이 정한다.

원칙(사용자 지시): "팝으로", "밝게" 같은 스타일 선택을 코드나 프롬프트에 하드코딩하지
않는다. 노드마다 LLM(Gemini/Claude)이 문맥에 맞는 음악(장르·무드·다이내믹)을 고른다.
레퍼런스가 있으면 그 음악 무드를 힌트로 반영한다. LLM이 없을 때만 최소한의 중립값을 쓴다.
"""

from __future__ import annotations

import json

from .schema import HookCandidate, ModelSpec, MusicSpec, ProductSpec
from .text_client import TextClient

_PROMPT = (
    "You are a short-form music supervisor for beauty reels. You define an INSTRUMENTAL BACKGROUND "
    "MUSIC BED that sits UNDER the visuals — not a foreground song.\n"
    "Model reality (important, set expectations accordingly): the music generator (Lyria 3) is "
    "reliable at INSTRUMENTAL beds with a clearly specified genre, tempo, and energy contour, but it "
    "is NOT reliable at foreground vocal songs, lyrics, or hooks — AI vocals come out cheesy and "
    "amateur. So never aim for a vocal/topline-driven track. Aim for a tasteful, professional "
    "instrumental bed whose job is to carry TEMPO and VIBE quietly behind the video.\n"
    "Taste still matters: pick a polished, current, professional genre that fits the audience (young, "
    "social-first, predominantly female / Gen-Z, early-20s) — clean and modern, never elevator "
    "music, generic acoustic/whistle stock pop, or a tired corporate 'happy' loop. Deep/organic "
    "house, French touch / filtered disco-house, downtempo/chillwave, and lo-fi/jazzy beats are good "
    "professional-bed reference points (not a fixed menu). Fit THIS video's flow, not a default.\n"
    "MOST IMPORTANT — specify these three in FINE DETAIL, this is what makes the bed good:\n"
    "1) GENRE/style: concrete and specific (e.g. 'clean modern deep house, organic house'), not just "
    "'pop' or 'electronic'.\n"
    "2) TEMPO/rhythm: the groove and feel (e.g. 'steady four-on-the-floor, relaxed but driving') — "
    "the exact bpm is set separately to match the cut rhythm, so describe the RHYTHMIC FEEL here.\n"
    "3) DYNAMICS (energy contour / 강약): how energy moves across the clip — either an even, steady "
    "bed ('flat') or a gentle rise into the payoff ('build') — and describe it (e.g. 'soft intro, "
    "subtle lift toward the end, no big drop').\n"
    "Also name the key INSTRUMENTATION driving the track in detail (e.g. 'warm rolling sub bass, soft "
    "filtered chord stabs, crisp minimal hi-hats, gentle atmospheric pads') — without this the bed "
    "comes out thin and generic.\n"
    "Brief: {brief}\nProduct: {product}\nTone: {tone}\nCreator: {character}\n"
    "Editing energy (cut pacing): {pacing}\n{hook}\n{ref}\n"
    'Output raw JSON only (no markdown, no prose): '
    '{{"style": str, "mood": str, "type": str, "instrumentation": str, "dynamics_detail": str, '
    '"dynamics": "flat"|"build", "prominence": "background"|"prominent", "bgm": "bed"|"none", '
    '"sfx": bool}}. '
    "style is the concrete genre/production style; type is a short descriptor; instrumentation is the "
    "detailed instrument/sound palette; dynamics_detail is a short phrase describing the energy "
    "contour; dynamics is the coarse flag (build if energy rises to a payoff, else flat). prominence: "
    "'prominent' when the video is vibe/aesthetic-driven and narration is minimal/interjections, else "
    "'background' when narration carries the information (the bed stays instrumental either way). "
    "bgm: 'none' only when the concept works better with NO music bed (e.g. crisp ASMR/texture-"
    "forward), otherwise 'bed'. "
    "sfx: true ONLY when the edit calls for produced, non-diegetic effect sounds — transition "
    "whooshes on cuts, graphic/sparkle accents, a hook riser, or an ending jingle/ding (a punchy, "
    "'variety-show' edited feel). Weigh the HOOK design specifically: if the hook is built for a "
    "punchy impact moment (a bold reveal, a stop-scrolling beat, a snappy variety-show open), a "
    "produced accent like a hook riser or whoosh can earn its place; if the hook is calm, clean, or "
    "sensorial (texture/ASMR-forward), keep sfx false. Let the hook's need for impact drive the "
    "call, not habit. Do NOT set sfx for natural in-scene sounds (spray, tap, pour) — the video "
    "model renders those. Default false unless the concept clearly wants that produced edit."
)


def _extract_json(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    start, end = s.find("{"), s.rfind("}")
    return s[start : end + 1] if start != -1 and end > start else s


def _hook_hint(hook: HookCandidate | None) -> str:
    """후크 설계를 music 노드가 SFX(임팩트 액센트) 판단에 참고할 한 줄 힌트로 만든다.

    후크가 텍스트 없이 비주얼/사운드로만 치고 나가거나(no_text_visual) command형이면 임팩트
    액센트가 어울릴 수 있고, 차분/센서리 후크면 무음이 낫다. 결정은 LLM이 한다(여기선 힌트만).
    """
    if hook is None:
        return "Hook design: unspecified."
    bits = []
    if hook.headline:
        bits.append(f"headline='{hook.headline}'")
    if hook.visual_direction:
        bits.append(f"visual='{hook.visual_direction}'")
    if hook.no_text_visual:
        bits.append("text-free visual/sound-led open")
    if hook.variant:
        bits.append(f"variant={hook.variant}")
    if hook.rationale:
        bits.append(f"why='{hook.rationale}'")
    return "Hook design (decide if it needs a produced impact accent): " + ("; ".join(bits) or "minimal")


def derive_music(
    brief: str,
    product: ProductSpec,
    tone: list[str],
    reference_music: MusicSpec | None,
    text_client: TextClient | None,
    character: ModelSpec | None = None,
    pacing: str | None = None,
    hook: HookCandidate | None = None,
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
                    hook=_hook_hint(hook),
                    ref=ref_hint,
                ),
                temperature=0.7,
            )
            data = json.loads(_extract_json(raw))
            style = str(data.get("style") or "").strip() or ref.style
            mood = str(data.get("mood") or "").strip() or ref.mood
            type_ = str(data.get("type") or "").strip() or ref.type
            instrumentation = str(data.get("instrumentation") or "").strip() or ref.instrumentation
            dynamics = str(data.get("dynamics") or "").strip() or ref.dynamics
            dynamics_detail = str(data.get("dynamics_detail") or "").strip() or ref.dynamics_detail
            prominence = "prominent" if str(data.get("prominence", "")).strip().lower() == "prominent" else "background"
            bgm = "none" if str(data.get("bgm", "")).strip().lower() == "none" else "bed"
            sfx = bool(data.get("sfx", False))
            # 보컬은 아예 시도하지 않는다(사용자 지시): AI 보컬은 촌스럽고 Lyria 3가 신뢰도 낮다.
            # BGM은 항상 인스트루멘털 배경 베드다(vocal=False 고정).
            if style or mood or type_:
                return MusicSpec(
                    mood=mood, style=style, type=type_, instrumentation=instrumentation,
                    dynamics=dynamics, dynamics_detail=dynamics_detail, tempo=ref.tempo,
                    prominence=prominence, vocal=False, bgm=bgm, sfx=sfx,
                )
        except Exception:
            pass

    # LLM이 없거나 실패: 레퍼런스 음악을 그대로 쓰고, 그것도 없으면 톤 첫 단어를 무드로만 둔다.
    if ref.mood or ref.style or ref.dynamics or ref.tempo:
        return ref
    return MusicSpec(mood=(tone[0] if tone else None), tempo=ref.tempo)
