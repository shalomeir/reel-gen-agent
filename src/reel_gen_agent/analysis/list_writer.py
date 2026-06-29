"""VideoProfile을 reference_video/list.md 항목 마크다운으로 변환한다."""

from __future__ import annotations

from .profile import VideoProfile


def _join(values, sep=", ") -> str:
    """리스트를 보기 좋게 잇는다. 비면 빈 문자열."""
    return sep.join(str(v) for v in values if v)


def to_list_entry(profile: VideoProfile, title: str, index: int) -> str:
    """프로필 한 개를 list.md의 한 항목(마크다운 블록)으로 만든다.

    기존 항목 형식(출처/규격/편집/내용/음악/넣은 의도)을 따른다.
    의도(넣은 의도)는 사람이 채우는 자리라 placeholder를 남긴다.
    """
    c = profile.container
    cut = profile.cut
    music = profile.music
    src = profile.source

    lines = [f"### {index}. {title}"]

    # 출처
    origin = src.url or (src.path or "")
    lines.append(f"- 출처: {origin}")

    # 규격
    spec = f"{c.resolution or '?'} ({c.aspect_ratio or '?'})"
    if c.fps:
        spec += f", {c.fps:g}fps"
    if c.duration_sec:
        spec += f", {c.duration_sec:g}초"
    lines.append(f"- 규격: {spec}")

    # 편집
    edit = f"{cut.count}컷"
    if cut.mean_sec:
        edit += f", 평균 {cut.mean_sec:g}초/컷"
    if cut.min_sec is not None and cut.max_sec is not None:
        edit += f" (범위 {cut.min_sec:g}~{cut.max_sec:g}초)"
    if cut.mode:
        edit += f". 모드 `{cut.mode}`"
    lines.append(f"- 편집: {edit}")

    # 내용/톤
    if profile.tone:
        lines.append(f"- 톤: {_join(profile.tone)}")
    if profile.narrative_arc:
        lines.append(f"- 내러티브: {' → '.join(profile.narrative_arc)}")

    # 자막
    sub = profile.subtitle
    if sub.position or sub.density or sub.text:
        bits = []
        if sub.position:
            bits.append(f"위치 {sub.position}")
        if sub.density:
            bits.append(f"밀도 {sub.density}")
        if sub.font_style:
            bits.append(sub.font_style)
        if sub.emoji:
            bits.append("이모지 " + _join(sub.emoji, " "))
        lines.append(f"- 자막: {_join(bits)}")

    # 보이스
    if profile.voice.present:
        v = profile.voice
        lines.append(f"- 보이스: {v.tone or '있음'}" + (f" ({v.pace})" if v.pace else ""))

    # 음악
    music_bits = []
    if music.dynamics:
        music_bits.append(f"다이내믹 {music.dynamics}")
    if music.bpm:
        music_bits.append(f"{music.bpm:g}bpm")
    if music.beat_synced is not None:
        music_bits.append("비트동기" if music.beat_synced else "의미기반 컷")
    if music_bits:
        lines.append(f"- 음악: {_join(music_bits)}")

    # 묘사(Gemini)
    if profile.description:
        lines.append(f"- 느낌: {profile.description}")

    # 의도: 사람이 채우는 자리
    lines.append("- 넣은 의도: (작성 필요)")

    return "\n".join(lines) + "\n"
