"""describe 노드: verify 통과 후 업로드용 자산(UploadKit -> upload.md)."""

from __future__ import annotations

from .schema import OutlineItem, ReelProfile, UploadKit


def _mmss(t: float) -> str:
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def build_upload_kit(profile: ReelProfile) -> UploadKit:
    title = profile.objective.key_message or f"{profile.product.name} | {profile.objective.goal}"
    outline = [
        OutlineItem(
            timecode=_mmss(p.t_start or 0.0),
            content=(p.beat or p.subtitle_text or f"shot {p.index}"),
        )
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
