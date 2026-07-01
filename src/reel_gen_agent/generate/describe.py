"""describe 노드: verify 통과 후 업로드용 자산(UploadKit -> upload.md)."""

from __future__ import annotations

from .schema import OutlineItem, ReelProfile, UploadKit


def _mmss(t: float) -> str:
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def _clean(s: str | None) -> str:
    return (s or "").strip()


def build_upload_kit(profile: ReelProfile) -> UploadKit:
    """유튜브 업로드용 제목·구조·본문을 영상 '콘텐츠'에서 만든다.

    유저가 chat에서 친 지시문(objective.goal)이나 그로부터 유도된 key_message는 쓰지 않는다.
    그건 시스템에 내리는 명령이지 시청자가 볼 카피가 아니다(예전엔 이게 제목·본문으로 새어
    나갔다). 제목은 훅 헤드라인(첫 3초 화면 문구)을 우선하고, 본문은 훅 문구 + 실제 대사/자막 +
    제품명으로 짠다. 훅이 없으면 제품 중심으로 폴백한다.
    """
    product = _clean(profile.product.name) or "this product"
    hook = profile.style.hook
    headline = _clean(hook.headline if hook else "")
    bottom = _clean(hook.bottom_caption if hook else "")

    # 제목: 훅 헤드라인 > 하단 카피+제품 > 제품. 명령성 필드(goal/key_message)는 쓰지 않는다.
    title = headline or (f"{bottom} | {product}" if bottom else product)

    outline = [
        OutlineItem(
            timecode=_mmss(p.t_start or 0.0),
            content=(_clean(p.subtitle_text) or _clean(p.beat) or f"shot {p.index}"),
        )
        for p in profile.storyboard.panels
    ]

    # 본문: 실제 대사(나레이션) 우선, 없으면 자막에서 몇 줄. 훅 문구를 앞세우고 제품명을 포함한다.
    spoken = [_clean(ln.text) for ln in profile.narration.lines if _clean(ln.text)]
    if not spoken:
        spoken = [_clean(p.subtitle_text) for p in profile.storyboard.panels if _clean(p.subtitle_text)]
    lead = " ".join(x for x in (headline, bottom) if x)
    caption = " ".join(x for x in (lead, " ".join(spoken[:4])) if x).strip()
    if product.lower() not in caption.lower():
        caption = f"{caption} Featuring {product}.".strip()
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
