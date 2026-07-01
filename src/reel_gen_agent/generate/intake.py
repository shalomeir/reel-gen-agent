"""입력 판별. 텍스트 브리프/단일 에셋/느슨한 입력 파일을 Objective+AssetInput으로 푼다.

판별 규칙 정본은 specs/product-design.md. 라벨 우선, 없으면 미디어 종류로 추정.
기본 로케일은 영어·미국.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .schema import AssetInput, GenerationInput, Objective

_URL = re.compile(r"https?://\S+")
_PATH = re.compile(r"\.?/?\S+\.(?:mp4|mov|jpg|jpeg|png|webp)", re.IGNORECASE)
_VIDEO_EXT = (".mp4", ".mov")
_IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")
_VIDEO_URL_HOSTS = (
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "instagram.com",
    "vimeo.com",
)
_LABEL_NAMES = (
    "제품 URL",
    "제품 url",
    "product URL",
    "product url",
    "product_url",
    "제품 이미지",
    "product image",
    "product_image",
    "캐릭터 이미지",
    "character image",
    "character_image",
    "모델 이미지",
    "model image",
    "model_image",
    "제품",
    "product",
    "캐릭터",
    "character",
    "모델",
    "레퍼런스 영상",
    "레퍼런스",
    "reference",
    "언어",
    "language",
    "locale",
)


@dataclass
class IntakeResult:
    objective: Objective | None
    character: AssetInput
    product: AssetInput
    reference_ref: str | None
    raw_brief: str | None
    product_url: str | None = None
    language: str | None = None
    # 발화 방식: on_camera / voiceover / none. None이면 downstream 기본(voiceover).
    delivery: str | None = None
    # 캐릭터·제품 소스가 존재하는 로컬 이미지 파일이면 그 절대경로(에셋 생성의 참조 이미지로 쓴다).
    character_image: str | None = None
    product_image: str | None = None


def _local_image(src: str | None) -> str | None:
    """소스가 존재하는 로컬 이미지 파일이면 절대경로를, 아니면 None을 돌려준다.

    입력으로 받은 인물/제품 이미지를 에셋 생성 단계의 참조(image-to-image)로 주입하기 위한
    해소기다(specs/product-design.md '판별 규칙': 인물 이미지→캐릭터, 제품 이미지→제품). URL은
    여기서 다루지 않는다(로컬 파일만).
    """
    if not src:
        return None
    path = Path(src).expanduser()
    if path.suffix.lower() in _IMAGE_EXT and path.exists():
        return str(path.resolve())
    return None


def _labeled(raw: str, labels: list[str]) -> str | None:
    for label in labels:
        other_labels = "|".join(re.escape(name) for name in _LABEL_NAMES)
        m = re.search(
            rf"{re.escape(label)}\s*[:：]\s*([^\n]+?)(?=\s+(?:{other_labels})\s*[:：]|$)",
            raw,
            re.MULTILINE,
        )
        if m:
            return m.group(1).strip()
    return None


def _clean_token(token: str) -> str:
    """자연어 문장 안 URL/경로 끝에 붙은 문장부호를 걷어낸다."""
    return token.strip().strip(".,;:!?)]}\"'”’。…")


def _is_video_url(src: str | None) -> bool:
    """플랫폼 영상 URL 또는 직접 mp4/mov URL이면 레퍼런스 영상으로 본다."""
    if not src:
        return False
    token = _clean_token(src)
    lower = token.lower()
    if lower.endswith(_VIDEO_EXT):
        return True
    try:
        host = urlparse(token).netloc.lower()
    except Exception:
        return False
    if host.startswith("www."):
        host = host[4:]
    return any(host == h or host.endswith(f".{h}") for h in _VIDEO_URL_HOSTS)


def _image_by_context(raw: str, keywords: tuple[str, ...]) -> str | None:
    """자연문 안 이미지 경로를 같은 줄 주변 키워드로 분류한다.

    `모델 이미지는 ./m.png`처럼 콜론 없는 자유 입력에서도 경로가 에셋 ref로 사라지지 않게 한다.
    """
    for match in _PATH.finditer(raw):
        token = _clean_token(match.group(0))
        if not token.lower().endswith(_IMAGE_EXT):
            continue
        line_start = raw.rfind("\n", 0, match.start()) + 1
        line_end = raw.find("\n", match.end())
        if line_end == -1:
            line_end = len(raw)
        context = raw[line_start:line_end].lower()
        if any(keyword.lower() in context for keyword in keywords):
            return token
    return None


def _join_bits(bits: list[str | None]) -> str:
    """수동 JSON 입력의 여러 자연어 필드를 한 줄 브리프 조각으로 합친다."""
    return " / ".join(bit.strip() for bit in bits if bit and bit.strip())


def _resolve_input_path(src: str | None, base_dir: str | Path | None) -> str | None:
    """GenerationInput 안의 로컬 상대경로를 입력 파일 위치 기준 절대경로로 바꾼다."""
    if not src:
        return None
    path = Path(src).expanduser()
    if path.is_absolute() or base_dir is None:
        return str(path)
    return str((Path(base_dir) / path).resolve())


def generation_input_to_brief(
    gen_input: GenerationInput, base_dir: str | Path | None = None
) -> str:
    """GenerationInput JSON을 기존 자연어 intake 경로가 이해하는 브리프로 변환한다.

    plan 그래프는 자연어 브리프를 중심으로 제품 URL/캐릭터/레퍼런스를 분류한다. 수동 템플릿
    JSON도 같은 경로를 타게 해 입력 계약은 넓히되, downstream 그래프는 한 곳으로 유지한다.
    """
    product = gen_input.product
    product_desc = _join_bits(
        [
            product.name,
            product.usp,
            product.spec,
            product.packaging_desc,
            product.category,
            product.form,
            ", ".join(product.colors),
            ", ".join(product.key_features),
            ", ".join(product.affordances),
            # 제품 알맹이(효능·성분·사용법·설명)도 브리프에 실어 downstream 카피가 빈약해지지 않게 한다.
            ", ".join(product.benefits),
            ", ".join(product.key_ingredients),
            product.how_to_use,
            product.description,
        ]
    )
    character_desc = _join_bits(
        [
            gen_input.model.name,
            gen_input.model.age,
            gen_input.model.gender,
            gen_input.model.look,
            gen_input.model.body,
            gen_input.model.wardrobe,
        ]
    )
    style_desc = _join_bits(
        [
            gen_input.style_prompt,
            ", ".join(gen_input.style.tone),
            gen_input.style.pacing,
            gen_input.style.cut_mode,
            ", ".join(gen_input.style.palette),
            gen_input.style.realism,
            ", ".join(gen_input.narrative_arc),
        ]
    )

    lines: list[str] = []
    if gen_input.prompt:
        lines.append(gen_input.prompt.strip())
    lines.extend(
        [
            f"영상 목적: {gen_input.objective or f'{product.name} 숏폼 제품 광고'}",
            f"제품: {product_desc or product.name}",
        ]
    )
    if product.url:
        lines.append(f"제품 URL: {product.url}")
    product_path = _resolve_input_path(product.path, base_dir)
    if product_path:
        lines.append(f"제품 이미지: {product_path}")
    character_path = _resolve_input_path(gen_input.model.path, base_dir)
    if character_path:
        lines.append(f"캐릭터 이미지: {character_path}")
    if character_desc:
        lines.append(f"캐릭터: {character_desc}")
    if style_desc:
        lines.append(f"스타일: {style_desc}")
    if gen_input.meta.language:
        lines.append(f"언어: {gen_input.meta.language}")
    if gen_input.delivery:
        lines.append(f"발화: {gen_input.delivery}")
    return "\n".join(lines)


def _goal_text(raw: str) -> str:
    """라벨(제품:/reference: 등) 값·URL·파일경로를 걷어낸 '목적' 서술 텍스트만 남긴다."""
    text = _URL.sub(" ", raw)
    text = _PATH.sub(" ", text)
    # "라벨: 값" 형태에서 값만 짧게 붙는 제품/캐릭터/레퍼런스 라벨 토큰을 제거(목적 라벨은 보존).
    for label in (
        "제품",
        "product",
        "캐릭터",
        "character",
        "모델",
        "레퍼런스 영상",
        "레퍼런스",
        "reference",
    ):
        text = re.sub(rf"{label}\s*[:：]\s*\S+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_PURPOSE_PROMPT = (
    "You validate input for a short-form video ad generator. Does the input clearly state the "
    "PURPOSE/GOAL of the video to make (what it advertises or is for, e.g. a product and the intent)? "
    "A bare filename/URL or a vague 'make a video' is NOT a clear purpose.\n"
    "Input: {brief}\n"
    'Reply raw JSON only: {{"ok": bool, "reason": str}}. reason: if not ok, one line on what is missing.'
)

_NORMALIZE_PROMPT = """
You repair rough input for a one-person product-focused vertical short video generator.
The input may be valid JSON, broken JSON, pasted notes, or plain natural language.

Extract and infer the planning facts that are useful for generation:
- video objective / purpose
- product name or natural-language product description
- product URL if explicitly present
- character/model type
- expected style, tone, pacing, mood
- expected language/locale
- reference video/image path or URL if explicitly present

Do not invent a product URL. Keep uncertain fields null, but infer a reasonable objective,
character, and style from the user's words when possible. Preserve Korean if the input is Korean.

Return raw JSON only with this shape:
{{
  "objective": "natural-language video purpose",
  "product": "natural-language product name and description",
  "product_url": "https://... or null",
  "character": "natural-language character/model type or null",
  "style": "natural-language style/tone/pacing/mood or null",
  "language": "ko/en/etc or null",
  "reference": "reference path or URL or null"
}}

Input:
{raw}
""".strip()


def validate_purpose(raw: str, text_client=None) -> tuple[bool, str]:
    """입력에 '영상의 목적'이 제대로 서술됐는지 판정한다. (ok, 사유).

    라벨/URL/경로를 걷어낸 목적 텍스트가 너무 얇으면 즉시 거절. LLM이 있으면 목적 명료성을
    한 번 더 판단하고(부실하면 거절), 없으면 최소 단어수 휴리스틱만 쓴다. ok=True면 그 목적만
    으로 나머지(캐릭터·제품·환경·음악 등)를 추론해 ReelProfile을 만든다.
    """
    goal = _goal_text(raw)
    if len(goal.split()) < 3:
        return (
            False,
            "영상의 목적(무엇을 위한 어떤 영상인지)이 서술되지 않았습니다. 목적을 적어주세요.",
        )
    if text_client is not None:
        try:
            import json as _json

            out = text_client.complete(_PURPOSE_PROMPT.format(brief=raw.strip()), temperature=0.0)
            s = out.strip()
            start, end = s.find("{"), s.rfind("}")
            data = _json.loads(s[start : end + 1]) if start != -1 and end > start else {}
            if not bool(data.get("ok", True)):
                return False, str(data.get("reason") or "영상의 목적이 명확하지 않습니다.")
        except Exception:
            pass  # LLM 판정 실패 -> 휴리스틱 통과로 진행
    return True, ""


def _json_object(raw: str) -> dict:
    """LLM 응답에서 첫 JSON object만 꺼낸다.

    모델이 설명 문장을 붙이거나 markdown fence를 둘러도 입력 정규화가 전체 실행을 막지 않게
    가장 바깥 object 후보만 좁게 파싱한다.
    """
    s = raw.strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        data = json.loads(s[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def normalized_input_to_brief(raw: str, text_client=None, base_dir: str | Path | None = None) -> str:
    """깨진 JSON/자연어/메모 형태 입력을 plan 그래프용 라벨 브리프로 정규화한다.

    이 함수는 "입력 파일이 반드시 JSON"이라는 가정을 버리기 위한 진입점이다. 유효한
    `GenerationInput`이면 스키마 기반으로 손실 없이 변환하고, 그 외에는 LLM이 읽기 쉬운
    라벨 브리프로 한 번 정리한다. LLM이 없거나 실패하면 원문을 그대로 넘긴다.
    """
    stripped = raw.strip()
    if not stripped:
        return ""
    try:
        gen_input = GenerationInput.model_validate_json(stripped)
    except Exception:
        pass
    else:
        return generation_input_to_brief(gen_input, base_dir=base_dir)

    if text_client is None:
        return stripped

    try:
        out = text_client.complete(_NORMALIZE_PROMPT.format(raw=stripped), temperature=0.0)
    except Exception:
        return stripped

    data = _json_object(out)
    if not data:
        return stripped

    lines: list[str] = []
    objective = data.get("objective")
    product = data.get("product")
    product_url = data.get("product_url")
    character = data.get("character")
    style = data.get("style")
    language = data.get("language")
    reference = data.get("reference")

    if isinstance(objective, str) and objective.strip():
        lines.append(f"영상 목적: {objective.strip()}")
    if isinstance(product, str) and product.strip():
        lines.append(f"제품: {product.strip()}")
    if isinstance(product_url, str) and product_url.strip():
        lines.append(f"제품 URL: {product_url.strip()}")
    if isinstance(character, str) and character.strip():
        lines.append(f"캐릭터: {character.strip()}")
    if isinstance(style, str) and style.strip():
        lines.append(f"스타일: {style.strip()}")
    if isinstance(language, str) and language.strip():
        lines.append(f"언어: {language.strip()}")
    if isinstance(reference, str) and reference.strip():
        lines.append(f"레퍼런스: {reference.strip()}")
    return "\n".join(lines) or stripped


def _normalize_delivery(value: str | None) -> str | None:
    """발화 방식 문자열을 on_camera/voiceover/none으로 정규화한다. 못 알아보면 None(기본 유지)."""
    if not value:
        return None
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    if "on_camera" in v or "oncamera" in v:
        return "on_camera"
    if v in ("none", "no_voice", "silent"):
        return "none"
    if "voiceover" in v or "voice_over" in v or "narration" in v:
        return "voiceover"
    return None


def intake(raw: str) -> IntakeResult:
    product_url = _labeled(
        raw, ["제품 URL", "제품 url", "product URL", "product url", "product_url"]
    )
    language = _labeled(raw, ["언어", "language", "locale"])
    delivery = _normalize_delivery(
        _labeled(raw, ["발화", "발화 방식", "delivery", "voice_mode", "voice mode"])
    )
    product_src = _labeled(raw, ["제품", "product"])
    product_image_src = _labeled(raw, ["제품 이미지", "product image", "product_image"])
    character_src = _labeled(raw, ["캐릭터", "character", "모델"])
    character_image_src = _labeled(
        raw,
        [
            "캐릭터 이미지",
            "character image",
            "character_image",
            "모델 이미지",
            "model image",
            "model_image",
        ],
    )
    character_image_src = character_image_src or _image_by_context(
        raw, ("캐릭터", "모델", "character", "model")
    )
    product_image_src = product_image_src or _image_by_context(raw, ("제품", "상품", "product"))
    ref_src = _labeled(raw, ["레퍼런스 영상", "레퍼런스", "reference"])
    if ref_src is None:
        for tok in _URL.findall(raw) + _PATH.findall(raw):
            tok = _clean_token(tok)
            if _is_video_url(tok):
                ref_src = tok
                break
    # 라벨이 없어도 비영상 URL은 제품 판매 페이지로 본다(제품 URL→제품). 구조화 product가 이미
    # 있어도 prompt 안에 "제품 url은 ..."처럼 넣은 근거 URL을 보존해야 한다.
    for tok in _URL.findall(raw):
        tok = _clean_token(tok)
        if tok == ref_src or _is_video_url(tok):
            continue
        product_url = product_url or tok
        if product_src is None:
            product_src = tok
        break
    product = AssetInput(kind="product", source=product_src, present=product_src is not None)
    character = AssetInput(
        kind="character", source=character_src, present=character_src is not None
    )
    objective = Objective(goal=raw.strip()) if raw.strip() else None
    return IntakeResult(
        objective=objective,
        character=character,
        product=product,
        reference_ref=ref_src,
        raw_brief=raw.strip() or None,
        product_url=product_url,
        language=language,
        delivery=delivery,
        character_image=_local_image(character_image_src) or _local_image(character_src),
        product_image=_local_image(product_image_src) or _local_image(product_src),
    )
