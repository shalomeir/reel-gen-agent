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


def _build_arguments(
    model: str,
    start_url: str,
    ref_urls: list[str],
    duration_sec: float,
    prompt: str,
    generate_audio: bool,
) -> dict:
    """fal 입력 인자를 만든다. reference-to-video면 start_image_url+image_urls, 아니면 image_url.

    IO(업로드·다운로드)와 분리해 fal 스키마 매핑만 단위 테스트할 수 있게 뺐다.
    """
    dur = str(max(_MIN_SEC, min(_MAX_SEC, int(round(duration_sec)))))
    args: dict = {
        "prompt": _fit_prompt(prompt or "cinematic vertical short, the product in focus"),
        "duration": dur,
    }
    if generate_audio:
        args["generate_audio"] = True
    if "reference-to-video" in model:
        args["start_image_url"] = start_url
        args["aspect_ratio"] = "9:16"
        if ref_urls:
            args["image_urls"] = ref_urls[:4]  # 외모 참조 최대 4장(@Image1..)
    else:
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
    ) -> str:
        import fal_client

        start_url = fal_client.upload_file(Path(still_path))
        # reference-to-video면 외모 참조 이미지(캐릭터/제품)도 업로드해 함께 넣는다.
        ref_urls: list[str] = []
        if "reference-to-video" in self.model:
            refs = [r for r in (reference_images or []) if r and Path(r).exists()]
            ref_urls = [fal_client.upload_file(Path(r)) for r in refs[:4]]
        arguments = _build_arguments(
            self.model, start_url, ref_urls, duration_sec, prompt, generate_audio
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
        cmd = ["ffmpeg", "-y", "-i", raw, "-t", f"{duration_sec:.3f}", "-vf", vf, "-r", str(fps)]
        cmd += (["-c:a", "aac"] if generate_audio else ["-an"])
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", out_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path
