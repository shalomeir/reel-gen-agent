"""페이싱(컷 리듬 성격) -> 편집 에너지·컷 지시문.

레퍼런스가 빠른 몽타주냐 느린 시연이냐에 따라 스토리보드 에너지와 영상 모델 편집 지시가
달라져야 한다. 이 값을 코드에 박지 않고 style.pacing(=레퍼런스 cut.mode)에서 유도한다.
같은 시스템이 다른 레퍼런스면 다른 편집 결을 내게 하는 스위치다(specs/similarity-loop.md R2).
"""

from __future__ import annotations


def _norm(pacing: str | None) -> str:
    """pacing 라벨을 fast/slow/mixed 세 갈래로 정규화한다."""
    p = (pacing or "").strip().lower()
    if "fast" in p or "montage" in p:
        return "fast"
    if "slow" in p or "demo" in p:
        return "slow"
    return "mixed"


def storyboard_energy(pacing: str | None) -> str:
    """스토리보드 플래너에 줄 '에너지' 원칙 한 줄. 페이싱에 맞는 컷·움직임 강도를 지시한다."""
    kind = _norm(pacing)
    if kind == "fast":
        return (
            "Pace: FAST montage. Punchy, high-energy cuts; quick, snappy shot changes; brisk "
            "movement and fast, decisive camera moves. Keep each cut short and driving."
        )
    if kind == "slow":
        return (
            "Pace: SLOW, sensorial demo. Calm and unhurried; let each moment breathe with longer "
            "holds; smooth, gentle, slow camera drifts; minimal cutting. Never busy or frantic."
        )
    return (
        "Pace: balanced/dynamic. Vary energy across the video; mix longer holds with a few quicker "
        "cuts; purposeful but not frantic camera moves."
    )


def motion_directive(motion: str | None) -> str:
    """샷 내부 모션 강도 지시문. 컷 빈도(pacing)와 별개로 카메라·피사체 움직임의 결을 정한다.

    빠른 컷이라도 샷 안은 부드러울 수 있다(레퍼런스1). None/모름이면 빈 문자열(중립).
    """
    m = (motion or "").strip().lower()
    if m == "gentle":
        return (
            "Within each shot keep motion gentle and smooth: slow, subtle camera moves and calm, "
            "minimal, graceful subject motion — not busy or energetic, even though cuts are quick."
        )
    if m == "dynamic":
        return (
            "Within each shot keep motion dynamic and lively: energetic subject movement and "
            "expressive camera moves."
        )
    if m == "still":
        return "Within each shot keep motion minimal: nearly still framing with only the slightest drift."
    return ""


def edit_directive(pacing: str | None) -> str:
    """영상 모델 멀티샷 프롬프트에 줄 '편집 결' 한 줄. 컷 전환의 성격을 지시한다."""
    kind = _norm(pacing)
    if kind == "fast":
        return (
            "a fast-edited sequence with hard, snappy cuts on a tight timeline (each shot brief and "
            "driving)"
        )
    if kind == "slow":
        return (
            "a smoothly edited sequence with longer, gentle holds and soft transitions (each shot "
            "lingers, calm and unhurried)"
        )
    return "an edited sequence with varied pacing (a mix of longer holds and quicker cuts)"
