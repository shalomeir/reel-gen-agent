"""storyboard 노드: 패널 목록과 콘티를 만든다(항상). 컷별 이미지는 조건부.

무엇을 보여줄지는 템플릿(narrative_arc), 얼마나 빠르게는 페이싱/style_profile 컷 데이터가
정한다. 패널 0은 항상 후크다. 컷별 start image 생성(Nano Banana)은 보통 불필요하고,
여러 컷이 복잡하게 다른 유형으로 짜인 영상일 때만 켠다(needs_panel_images).
"""

from __future__ import annotations

from pathlib import Path

from .image_client import ImageClient
from .schema import (
    EnvironmentSpec,
    InputMeta,
    ModelSpec,
    ProductSpec,
    Storyboard,
    StoryboardPanel,
    StyleDimensions,
)
from .templates import PRODUCT_LOCK_BEATS, shot_for, template_for

# 페이싱 -> 평균 컷 길이(초). 컷 수 시딩에 쓴다.
_AVG_CUT_SEC = {"fast_montage": 1.2, "mixed": 2.5, "slow_demo": 4.0}

# 얼굴용 뷰티 제품 힌트. 제품명에 이 단어가 있으면 더 타이트하게(얼굴 중심) 잡는다.
_FACE_BEAUTY_HINTS = (
    "serum",
    "cream",
    "toner",
    "essence",
    "ampoule",
    "moistur",
    "cleanser",
    "cushion",
    "foundation",
    "lip",
    "eyeshadow",
    "mask",
    "sunscreen",
    "skin",
    "spf",
    "세럼",
    "크림",
    "토너",
    "에센스",
    "쿠션",
    "선크림",
    "립",
)


def _framing_directive(product: ProductSpec) -> str:
    """세로형 인물 프레이밍 기본값. 인물을 크게, 기본은 상반신. 얼굴용 뷰티는 더 타이트.

    프레이밍 규칙 정본은 specs/trd.md "기본 제작 포맷".
    """
    name = (product.name or "").lower()
    if any(h in name for h in _FACE_BEAUTY_HINTS):
        return (
            "framing: vertical 9:16, subject very large — tight on the face, from the "
            "upper chest up so the face fills most of the frame (face beauty product)"
        )
    return "framing: vertical 9:16, subject large — upper body only by default"


def _panel_count(meta: InputMeta, style: StyleDimensions, cut_count: int | None) -> int:
    if cut_count and cut_count >= 2:
        return min(cut_count, 12)
    avg = _AVG_CUT_SEC.get(style.pacing or "mixed", 2.5)
    return max(2, min(12, round(meta.duration_sec / avg)))


def _global_prompt(
    style: StyleDimensions,
    product: ProductSpec,
    character: ModelSpec,
    environment: EnvironmentSpec,
) -> str:
    bits = [
        # 인물은 평범한 일반인이 아니라 매력적인 뷰티 인플루언서/틱톡커로 묘사한다(사용자 지시).
        f"character: an attractive, camera-ready beauty influencer / TikTok creator — "
        f"{character.look or character.name or 'magnetic good looks, healthy natural skin, subtle glam'}"
        ", natural realistic skin texture (not oily, wet or overly shiny, no plastic glossy sheen)",
        f"product: {product.name}",
        f"mood and tone: {', '.join(style.tone)}" if style.tone else "",
        _framing_directive(product),
        f"color grading in warm tones matching this palette: {', '.join(style.palette)}"
        if style.palette
        else "",
        f"location: {environment.location}" if environment.location else "",
        f"lighting: {environment.lighting}" if environment.lighting else "",
        f"mood: {environment.mood}" if environment.mood else "",
        # 자막은 편집단계에서 올리므로 이미지·영상에 글자가 찍히면 안 된다.
        "no on-screen text, captions, letters or watermarks",
    ]
    return "; ".join(b for b in bits if b)


# 메시지를 담는 beat에만 키워드 자막을 붙인다. 모든 컷에 강제하지 않는다(필러 자막 금지).
# 그 외 beat(problem/use/reaction 등)는 자막 없이 두고, 필요하면 기획이 채운다. {name}=제품명.
_BEAT_KEYWORDS: dict[str, str] = {
    "discovery": "meet {name}",
    "reveal": "meet {name}",
    "cta": "try {name}",
}


def _subtitle_for(
    beat: str, index: int, style: StyleDimensions, product: ProductSpec
) -> str | None:
    """의미 있는 컷에만 키워드 자막을 준다. 훅은 헤드라인, proof/benefit류는 usp, 리빌/CTA는
    제품 소개·행동 유도. 나머지 컷은 자막 없이 둔다(모든 컷 강제 금지)."""
    if index == 0 and style.hook and style.hook.headline:
        return style.hook.headline
    if beat in ("proof", "after", "result", "benefit") and product.usp:
        return product.usp
    template = _BEAT_KEYWORDS.get(beat)
    if template:
        return template.format(name=product.name)
    return None


def _expand_beats(template: list[str], n: int) -> list[str]:
    """템플릿 arc를 n개 컷에 '비례 분배'한다. 마지막 beat(cta)만 반복해 도배하지 않고, 중간
    beat들이 고르게 늘어나 서사 흐름을 유지한다. 항상 hook으로 시작하고 cta로 끝낸다.

    예) [hook, problem, use, reaction, proof, cta], n=9
      -> [hook, problem, problem, use, use, reaction, proof, proof, cta]
    (기존의 [..., cta, cta, cta, cta] 도배를 없앤다.)
    """
    if n <= 0 or not template:
        return []
    if n == 1:
        return [template[0]]
    last = len(template) - 1
    beats = [template[round(i * last / (n - 1))] for i in range(n)]
    beats[0] = "hook"
    if "cta" in template:
        beats[-1] = "cta"
    return beats


def build_storyboard(
    *,
    meta: InputMeta,
    style: StyleDimensions,
    product: ProductSpec,
    character: ModelSpec,
    environment: EnvironmentSpec,
    category: str | None = None,
    cut_count: int | None = None,
) -> Storyboard:
    """템플릿 + 페이싱(또는 style_profile 컷 수)으로 패널과 콘티를 만든다.

    cut_count가 주어지면(레퍼런스 시딩) 그 컷 수를, 없으면 페이싱으로 추정한다.
    """
    beats_template = template_for(category)
    n = _panel_count(meta, style, cut_count)
    beats = _expand_beats(beats_template, n)

    seg = meta.duration_sec / n
    global_prompt = _global_prompt(style, product, character, environment)
    panels: list[StoryboardPanel] = []
    for i, beat in enumerate(beats):
        shot = shot_for(beat)
        # beat "라벨 단어"(problem/cta 등)를 프롬프트에 넣으면 이미지 모델이 그 단어를 화면
        # 글자로 그려버린다. 라벨 대신 샷·피사체만 적는다.
        # 훅 컷은 생성된 훅의 시각 컨셉(visual_direction)을 그대로 반영해 첫 3초가 훅을 실현하게 한다.
        if beat == "hook" and style.hook and style.hook.visual_direction:
            local = f"{shot}, opening hook: {style.hook.visual_direction}"
        else:
            local = f"{shot} of {product.name}"
        if beat == "use" and product.affordances:
            local += f" ({product.affordances[0]})"
        panels.append(
            StoryboardPanel(
                index=i,
                beat=beat,
                t_start=round(i * seg, 2),
                t_end=round((i + 1) * seg, 2),
                shot_type=shot,
                subject_lock=True,
                product_lock=beat in PRODUCT_LOCK_BEATS,
                environment_lock=True,
                prompt=f"{global_prompt}. {local}",
                subtitle_text=_subtitle_for(beat, i, style, product),
            )
        )
    return Storyboard(global_prompt=global_prompt, panels=panels)


def needs_panel_images(storyboard: Storyboard) -> bool:
    """컷별 이미지 생성이 필요한가. 보통은 False.

    여러 컷이 서로 다른 유형으로 복잡하게 짜인 영상(컷 수가 많고 샷 타입이 다양)일 때만
    True. 단순/원컷 영상은 컷별 이미지를 미리 만들 필요가 없다.
    """
    panels = storyboard.panels
    distinct_shots = {p.shot_type for p in panels if p.shot_type}
    return len(panels) >= 5 and len(distinct_shots) >= 3


def generate_panel_images(
    storyboard: Storyboard,
    *,
    character_image: str | None,
    product_image: str | None,
    image_client: ImageClient,
    out_dir: str,
) -> Storyboard:
    """컷별 start image를 Nano Banana로 만든다(복잡한 멀티컷일 때만 호출).

    스토리보드 패널 묘사 + 캐릭터 이미지 + 제품 이미지를 reference로 넣어 "이 컷의 첫 장면"을
    생성한다. 일관성(얼굴·제품)을 reference로 잡는다.
    """
    panels_dir = Path(out_dir) / "panels"
    panels_dir.mkdir(parents=True, exist_ok=True)
    refs = [r for r in (character_image, product_image) if r]
    for panel in storyboard.panels:
        prompt = f"First frame of this cut. {panel.prompt or ''}".strip()
        out = str(panels_dir / f"start_{panel.index}.png")
        # 컷별 start image는 영상 생성 reference로 주입되므로 히어로(4K Pro)로 만든다.
        panel.still_image = image_client.generate(prompt, refs, out, hero=True)
    return storyboard
