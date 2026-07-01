"""fal.ai 영상 백엔드(Kling O3, Seedance 등). VideoBackend 인터페이스를 fal API로 구현한다.

Veo와 같은 시그니처(패널 하나 -> 클립)를 공유하되, fal은 잡 제출+폴링을 fal_client.subscribe가
내부에서 처리하므로 호출이 단순하다. 시작 이미지를 업로드해 URL로 넘기고, 결과 video.url을
내려받아 Veo와 동일하게 ffmpeg로 패널 길이·9:16·프레임레이트에 맞춘다.

모델 종류는 model id로 가른다:
- reference-to-video: start_image_url + image_urls(외모 참조 최대 4장, 캐릭터/제품). 캐릭터·제품
  일관에 유리(회고의 '최선 경로').
- image-to-video(기본, Kling/Seedance 공통): image_url(시작 프레임) 하나.
duration은 3~15초 자유라 Veo(4/6/8)보다 낭비가 적다. FAL_KEY는 fal_client가 자동으로 읽는다.
"""

from __future__ import annotations

import math
import os
import subprocess
import urllib.request
from pathlib import Path

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

_DEFAULT_MODEL = "fal-ai/kling-video/o3/standard/image-to-video"
_MIN_SEC = 3
_MAX_SEC = 15
# Kling은 prompt를 최대 2500자로 제한한다(초과하면 fal이 422로 거절 -> 켄번 폴백). Veo엔 이
# 제한이 없어 프롬프트가 길어졌는데, 그게 Kling에서만 실패의 원인이었다. 여기서 안전하게 맞춘다.
_MAX_PROMPT = 2500


def _fit_prompt(prompt: str) -> str:
    """프롬프트를 Kling 한도(2500자)에 맞춘다. 샷 리스트(끝)는 보존하고 앞의 장문 스타일 서술을
    줄인다 — 멀티샷의 핵심은 'Shot N:' 목록이라 그건 자르지 않는다."""
    if len(prompt) <= _MAX_PROMPT:
        return prompt
    marker = "\nShot 1:"
    i = prompt.find(marker)
    if i == -1:
        return prompt[:_MAX_PROMPT]
    head, shots = prompt[:i], prompt[i:]
    if len(shots) >= _MAX_PROMPT:
        return shots[:_MAX_PROMPT]
    keep = _MAX_PROMPT - len(shots)
    return head[:keep].rstrip() + shots


class _FalTransientError(RuntimeError):
    """fal 일시 오류(네트워크/큐/미완료). tenacity가 백오프 재시도한다."""


_MAX_REFS = 4  # elements + image_urls 합쳐 최대 4개(fal Kling O3 reference-to-video 제한).


def _build_arguments(
    model: str,
    start_url: str,
    duration_sec: float,
    prompt: str,
    generate_audio: bool,
    character_url: str | None = None,
    product_url: str | None = None,
    style_urls: list[str] | None = None,
) -> dict:
    """fal 입력 인자를 만든다. reference-to-video면 elements(인물·제품 정체성)+image_urls(스타일),
    아니면 image_url.

    캐릭터·제품 정체성은 `image_urls`(스타일/외모 참조)가 아니라 `elements`로 넣어야 일관성이
    산다(fal 스키마: elements = characters/objects, frontal_image_url로 정체성 고정, @Element1로
    프롬프트에서 참조). image_urls는 룩/조명 참조(@Image1)일 뿐 정체성 고정이 약하다. 예전엔
    캐릭터를 image_urls에 넣어 컷마다 인물이 딴 사람으로 드리프트했다. IO와 분리해 스키마 매핑만
    단위 테스트할 수 있게 뺐다.
    """
    # 올림(ceil)해서 요청한다. Kling은 정수초 클립을 주므로, 내림하면 분수 seg_dur(예: 9.494초)에
    # 대해 9초 클립이 와 계획보다 짧아진다. 그러면 마지막 서브컷이 실제 영상 끝을 넘겨 프리즈되고,
    # 그 프리즈가 세그먼트 경계 xfade offset을 밀어 다음 세그먼트가 통째 누락된다. 올림하면 클립이
    # 계획 이상이라 정확히 seg_dur로 trim되어 서브컷이 딱 맞는다(초과분 최대 1초는 trim으로 버린다).
    dur = str(max(_MIN_SEC, min(_MAX_SEC, math.ceil(duration_sec))))
    base_prompt = prompt or "cinematic vertical short, the product in focus"
    args: dict = {
        "duration": dur,
        # 항상 명시한다: False면 Kling이 제 배경음악을 깔지 않는다(빼면 모델 기본이 오디오를
        # 생성해 우리 BGM과 충돌·과다). 발화(integrated)일 때만 True로 씬 네이티브 음성을 받는다.
        "generate_audio": bool(generate_audio),
    }
    if "reference-to-video" in model:
        args["start_image_url"] = start_url
        args["aspect_ratio"] = "9:16"
        # 단일 생성(릴 전체) 안에서 Kling이 멀티샷 구조를 스스로 잡게 한다(AI Multi-Shot). 우리
        # 다운스트림 재분할은 hook 컷만 최소로 하고 나머지는 통짜라, 그 통짜 구간에 Kling의 네이티브
        # 샷 변화가 실려 단조로움을 던다(atlascloud Kling 3.0 캐릭터 일관성 가이드).
        args["shot_type"] = "intelligent"
        # elements: 캐릭터·제품 정체성 고정. frontal_image_url + reference_image_urls.
        elements: list[dict] = []
        tag_hints: list[str] = []
        if character_url:
            elements.append(
                {"frontal_image_url": character_url, "reference_image_urls": [character_url]}
            )
            tag_hints.append(
                f"@Element{len(elements)} is the SAME creator in every shot — identical face, "
                "ethnicity, skin tone, hair, and age; never a different person."
            )
        if product_url:
            elements.append(
                {"frontal_image_url": product_url, "reference_image_urls": [product_url]}
            )
            tag_hints.append(
                f"@Element{len(elements)} is the product — keep its exact shape, color, and label."
            )
        # image_urls(스타일/룩 참조)는 elements와 합쳐 최대 4개까지 남은 예산만큼만 싣는다.
        budget = max(0, _MAX_REFS - len(elements))
        imgs = [u for u in (style_urls or []) if u][:budget]
        img_tags = [
            f"@Image{i + 1} sets the look, lighting, and color mood." for i in range(len(imgs))
        ]
        if elements:
            args["elements"] = elements
        if imgs:
            args["image_urls"] = imgs
        # 태그를 프롬프트에 실어야 모델이 실제로 elements/image를 쓴다(안 실으면 참조가 약하게 반영).
        hint = " ".join(tag_hints + img_tags)
        args["prompt"] = _fit_prompt(f"{hint}\n{base_prompt}" if hint else base_prompt)
    else:
        args["prompt"] = _fit_prompt(base_prompt)
        args["image_url"] = start_url  # image-to-video(Kling/Seedance 공통)
    return args


def _download(url: str, out_path: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "reel-gen-agent"})
    with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310 (fal 결과 URL)
        data = resp.read()
    with open(out_path, "wb") as f:
        f.write(data)


class FalVideoBackend:
    """fal.ai Kling/Seedance 영상 백엔드. model id로 i2v / reference-to-video를 가른다."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("FAL_VIDEO_MODEL") or _DEFAULT_MODEL

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        retry=retry_if_exception_type(_FalTransientError),
    )
    def _subscribe(self, arguments: dict) -> dict:
        import fal_client

        try:
            return fal_client.subscribe(self.model, arguments=arguments, with_logs=False)
        except Exception as exc:  # 네트워크/큐/일시 오류는 재시도한다.
            raise _FalTransientError(f"fal 호출 오류: {exc}") from exc

    def render_panel(
        self,
        still_path: str,
        duration_sec: float,
        width: int,
        height: int,
        fps: int,
        out_path: str,
        motion: str = "",
        prompt: str = "",
        generate_audio: bool = False,
        reference_images: list[str] | None = None,
        character_ref: str | None = None,
        product_ref: str | None = None,
    ) -> str:
        import fal_client

        def _upload(p: str | None) -> str | None:
            return fal_client.upload_file(Path(p)) if p and Path(p).exists() else None

        start_url = fal_client.upload_file(Path(still_path))
        # reference-to-video면 캐릭터·제품은 elements(정체성 고정)로, 나머지 참조 이미지는
        # image_urls(스타일/룩)로 업로드해 넣는다. i2v는 시작 프레임만 쓰므로 업로드하지 않는다.
        character_url = product_url = None
        style_urls: list[str] = []
        if "reference-to-video" in self.model:
            character_url = _upload(character_ref)
            product_url = _upload(product_ref)
            style_urls = [
                u for u in (_upload(r) for r in (reference_images or [])) if u
            ][:_MAX_REFS]
        arguments = _build_arguments(
            self.model, start_url, duration_sec, prompt, generate_audio,
            character_url=character_url, product_url=product_url, style_urls=style_urls,
        )
        result = self._subscribe(arguments)
        video = (result or {}).get("video") or {}
        url = video.get("url")
        if not url:
            raise RuntimeError(f"fal이 영상을 반환하지 않았습니다({self.model}): {result}")

        raw = str(Path(out_path).with_suffix(".fal.mp4"))
        _download(url, raw)

        # 패널 길이로 자르고 9:16·목표 해상도/프레임레이트로 맞춘다(Veo와 동일한 마감).
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        cmd = ["ffmpeg", "-y", "-i", raw]
        if not generate_audio:
            # 비발화는 네이티브 오디오를 버리되 무음 트랙을 붙인다. 모든 클립이 오디오를 갖게 해
            # (ken_burns·Veo와 통일) concat·경계 크로스페이드에서 오디오 유무가 섞이지 않게 한다.
            cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        cmd += ["-t", f"{duration_sec:.3f}", "-vf", vf, "-r", str(fps)]
        if generate_audio:
            cmd += ["-c:a", "aac"]
        else:
            cmd += ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-shortest"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", out_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path
