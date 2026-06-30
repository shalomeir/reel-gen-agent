"""내러티브 아크 템플릿. 이름 있는 비트 구성으로 스토리보드의 "무엇을 보여줄지"를 정한다.

컷 수와 타이밍(얼마나 빠르게)은 style_profile/페이싱이 정하고, 템플릿(무엇을)과 리듬은
독립적으로 결합한다(docs/pipeline-design.md "컨셉 템플릿"). 상수가 아니라 데이터다.
"""

from __future__ import annotations

# 템플릿 이름 -> 비트 시퀀스. 첫 비트는 항상 hook이다.
NARRATIVE_TEMPLATES: dict[str, list[str]] = {
    "ugc_review": ["hook", "problem", "use", "reaction", "proof", "cta"],
    "before_after": ["hook", "before", "use", "after", "proof", "cta"],
    "unboxing": ["hook", "unbox", "reveal", "use", "reaction", "cta"],
    "tutorial_routine": ["hook", "step", "step", "step", "result", "cta"],
    "selfie_review": ["hook", "talk", "use", "talk", "proof", "cta"],
}

DEFAULT_TEMPLATE = "ugc_review"

# 카테고리 -> 기본 템플릿. 새 카테고리는 행 추가.
CATEGORY_TEMPLATE: dict[str, str] = {
    "launch": "unboxing",
    "skincare_efficacy": "before_after",
    "routine": "tutorial_routine",
    "info": "tutorial_routine",
    "demo": "before_after",
    "lifestyle": "selfie_review",
}

# 비트 -> 샷 타입. 없으면 medium.
SHOT_BY_BEAT: dict[str, str] = {
    "hook": "macro CU",
    "problem": "medium",
    "before": "medium",
    "unbox": "medium",
    "reveal": "macro CU",
    "use": "macro CU",
    "step": "medium",
    "reaction": "CU",
    "talk": "CU",
    "after": "medium",
    "result": "medium",
    "proof": "medium",
    "cta": "wide",
}

# 제품이 주인공인 비트(제품 에셋을 잠근다).
PRODUCT_LOCK_BEATS = {"use", "reveal", "proof", "after", "result", "cta", "unbox"}


def template_for(category: str | None) -> list[str]:
    """카테고리에 맞는 비트 시퀀스를 돌려준다(없으면 기본)."""
    name = CATEGORY_TEMPLATE.get(category or "", DEFAULT_TEMPLATE)
    return list(NARRATIVE_TEMPLATES.get(name, NARRATIVE_TEMPLATES[DEFAULT_TEMPLATE]))


def shot_for(beat: str) -> str:
    return SHOT_BY_BEAT.get(beat, "medium")
