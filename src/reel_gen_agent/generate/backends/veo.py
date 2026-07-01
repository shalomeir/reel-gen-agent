"""Veo 영상 백엔드. 패널 스틸 + 프롬프트로 image-to-video 클립을 만든다(Vertex / Gemini API 양쪽).

[ai-model-records.md] §4: Veo 3.1은 두 레인으로 호출한다. 어느 레인을 쓸지는 `select_backend()`가
정한다(`GENAI_BACKEND=auto`면 Vertex 우선, 자격이 없으면 `GEMINI_API_KEY`).
- Vertex AI lane: 출력이 GCS로 떨어진다(`VEO_OUTPUT_GCS_URI` 필수). GA 모델 ID(`veo-3.1-*-001`).
- Gemini Developer API lane: GCS 없이 File API로 바이트를 직접 내려받는다(`GEMINI_API_KEY`).
  preview 계열 모델 ID(`veo-3.1-*-preview`, `GEMINI_VEO_MODEL`로 지정).
Veo는 4/6/8초만 만들므로, 짧은 컷은 최소 길이로 생성한 뒤 패널 길이에 맞춰 자른다. voice는
나레이션(voiceover)이 기본이라 `generate_audio=False`로 둔다.

재시도 정책:
- 일시적 오류(네트워크/타임아웃/응답 없음)는 tenacity로 지수 백오프 재시도한다.
- RAI 필터로 빈 결과가 오면 프롬프트를 LLM이 분석해 정책 안전하게 다시 쓴 뒤 재시도한다
  (특정 도메인 단어 블록리스트 하드코딩 아님, 컨셉·샷·모션은 보존). LLM이 없으면 서술 수식을
  걷어내 장면 골격만 남기는 구조 기반 폴백을 쓴다.
모든 재시도가 실패하면 RuntimeError를 올려 호출 측이 켄 번스 스틸로 폴백하게 한다.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_ALLOWED_VEO_SEC = (4, 6, 8)
_POLL_SEC = 10
_MAX_WAIT_SEC = 600

# 진단용 최소 중립 프롬프트. RAI 빈 결과가 프롬프트 때문인지 입력 이미지 때문인지 가른다:
# 이 무해한 프롬프트로도 막히면(같은 이미지) 원인은 이미지다(프롬프트 완화로 못 뚫는다).
_MINIMAL_PROMPT = "a calm, tasteful vertical product video, gentle camera movement, clean footage"

# RAI 재작성 지시(원인이 '프롬프트'로 확인됐을 때만 쓴다). 방향을 살리며 트리거 어구만 완화.
_SOFTEN_INSTRUCTION = (
    "This image-to-video prompt was blocked by an automated content-safety filter, but the same "
    "image passes with a neutral prompt — so the wording is the trigger. Rewrite it to pass while "
    "preserving the same scene, shots, actions, camera movement, subject and product. Neutralize "
    "only the sensitive wording; keep it concrete and filmable. Return ONLY the rewritten prompt."
    "\n\nPROMPT:\n{prompt}"
)


class _VeoTransientError(RuntimeError):
    """일시적 Veo 오류(네트워크/타임아웃/미완료). tenacity가 이 예외만 재시도한다."""


class VeoImageRAIError(RuntimeError):
    """입력 스틸이 RAI 정책에 차단됨(프롬프트 무관, 최소 중립 프롬프트로도 실패).

    대개 생성 인물이 실존·식별 가능한 인물과 유사하거나 기타 콘텐츠 정책 사유다. 이 경우는
    프롬프트 완화로 못 뚫고 스틸 폴백으로 덮는 것도 부적절하므로(가짜 초상 광고 방지), 위로
    올려 production을 명시적으로 거절시킨다(사용자 지시). reason에 사유를 담아 CLI가 노출한다.
    """


def _veo_seconds(duration_sec: float) -> int:
    """패널 길이를 Veo가 만들 수 있는 최소 허용 길이로 올림한다(4/6/8)."""
    for s in _ALLOWED_VEO_SEC:
        if duration_sec <= s:
            return s
    return _ALLOWED_VEO_SEC[-1]


def _structural_fallback(prompt: str) -> str:
    """LLM 없이 쓰는 일반 완화. 도메인 단어에 의존하지 않고 장면 골격만 남긴다.

    첫 줄(장면 설정)과 'Shot N:' 줄들만 유지하고 나머지 서술 수식을 걷어낸다. 특정 단어를
    블록하지 않으므로 어떤 프롬프트에도 일반적으로 적용된다.
    """
    lines = [ln for ln in prompt.split("\n") if ln.strip()]
    if not lines:
        return "a vertical short-form clip, the product in focus, clean footage, no on-screen text"
    shots = [ln for ln in lines if ln.strip().lower().startswith("shot")]
    kept = [lines[0], *shots] if shots else lines[:1]
    return "\n".join(kept)


def _download_gcs(uri: str, out_path: str) -> None:
    """gs://bucket/blob -> 로컬 파일."""
    from google.cloud import storage

    assert uri.startswith("gs://"), uri
    bucket_name, _, blob_name = uri[len("gs://") :].partition("/")
    client = storage.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"))
    client.bucket(bucket_name).blob(blob_name).download_to_filename(out_path)


class VeoBackend:
    def __init__(self, model: str | None = None, text_client=None) -> None:
        self.model = model or os.environ.get("VEO_MODEL") or "veo-3.1-fast-generate-001"
        self.gcs_uri = os.environ.get("VEO_OUTPUT_GCS_URI")
        # RAI 재작성용 텍스트 LLM. 없으면 첫 필요 시 지연 생성(키 있으면), 그래도 없으면 구조 폴백.
        self._text_client = text_client
        self._text_client_resolved = text_client is not None

    def _resolve_model(self, backend: str) -> str:
        """레인에 맞는 Veo 모델 ID를 고른다.

        Gemini Developer API는 preview 계열 ID(`veo-3.1-*-preview`)를, Vertex는 GA
        ID(`veo-3.1-*-001`)를 쓴다. plan이 이미 레인에 맞는 ID를 넘기면 그대로 쓰되, 레인과
        어긋난 ID가 들어오면 해당 레인의 기본값으로 교정한다(교차 실행 방어).
        """
        is_preview = "preview" in (self.model or "").lower()
        if backend == "gemini" and not is_preview:
            return os.environ.get("GEMINI_VEO_MODEL") or "veo-3.1-fast-generate-preview"
        if backend == "vertex" and is_preview:
            return os.environ.get("VEO_MODEL") or "veo-3.1-fast-generate-001"
        return self.model

    def _get_text_client(self):
        """RAI 재작성에 쓸 텍스트 LLM을 지연 확보한다(키 없으면 None)."""
        if not self._text_client_resolved:
            self._text_client_resolved = True
            try:
                from ..text_client import make_text_client

                self._text_client = make_text_client()
            except Exception:
                self._text_client = None
        return self._text_client

    def _rewrite_prompt(self, prompt: str) -> str:
        """원인이 '프롬프트'로 확인됐을 때만 쓰는 재작성. LLM 우선, 없으면 구조 기반 폴백."""
        tc = self._get_text_client()
        if tc is not None:
            try:
                out = tc.complete(
                    _SOFTEN_INSTRUCTION.format(prompt=prompt), temperature=0.3
                ).strip()
                if out:
                    return out
            except Exception:
                pass  # LLM 재작성 실패 -> 구조 폴백
        return _structural_fallback(prompt)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        retry=retry_if_exception_type(_VeoTransientError),
    )
    def _generate_video(self, client, prompt: str, image, config):
        """한 번의 Veo 생성 시도. 성공 시 Video 객체, RAI 빈 결과면 None.

        일시적 오류(미완료/응답 없음/네트워크)는 _VeoTransientError로 올려 tenacity가 백오프
        재시도한다. RAI 필터로 결과가 비면 None을 돌려(예외 아님) 호출부가 프롬프트를 소프트닝해
        재시도하게 한다.
        """
        try:
            op = client.models.generate_videos(
                model=self.model,
                prompt=prompt or "cinematic vertical short, the product in focus",
                image=image,
                config=config,
            )
            waited = 0
            while not op.done and waited < _MAX_WAIT_SEC:
                time.sleep(_POLL_SEC)
                waited += _POLL_SEC
                op = client.operations.get(op)
        except _VeoTransientError:
            raise
        except Exception as exc:  # 네트워크/SDK 오류는 일시적으로 보고 재시도한다.
            raise _VeoTransientError(f"Veo 호출 오류: {exc}") from exc
        if not op.done or not getattr(op, "response", None):
            raise _VeoTransientError("Veo 생성 미완료/응답 없음")
        resp = op.response
        videos = resp.generated_videos or []
        if not videos:
            # RAI 필터로 빈 결과. 왜 막혔는지 사유를 노출한다(가능한 필드에서 최대한 수집).
            reasons = (
                getattr(resp, "rai_media_filtered_reasons", None)
                or getattr(op, "error", None)
                or "사유 미제공(응답에 rai_media_filtered_reasons 없음)"
            )
            count = getattr(resp, "rai_media_filtered_count", None)
            print(
                f"[veo] RAI 차단(빈 결과) count={count} 사유={reasons}",
                file=sys.stderr,
            )
            return None  # 프롬프트 소프트닝/재시도 신호
        return videos[0].video

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
        reference_images: list[str] | None = None,  # Veo는 시작 이미지만 쓴다(미사용).
        character_ref: str | None = None,  # Veo 미사용(Kling reference-to-video elements 전용).
        product_ref: str | None = None,  # Veo 미사용.
    ) -> str:
        from google.genai import types

        from ...analysis.gemini_client import make_client, select_backend

        selection = select_backend()
        if selection is None:
            raise RuntimeError("Veo 자격 없음(GEMINI_API_KEY 또는 Vertex 자격 필요).")
        backend = selection[0]
        # Vertex는 GCS 출력이 필수, Gemini API는 File API로 바이트를 직접 받으므로 GCS가 필요 없다.
        if backend == "vertex" and not self.gcs_uri:
            raise RuntimeError("Veo Vertex 레인은 VEO_OUTPUT_GCS_URI가 필요하다.")
        client = make_client(selection)
        self.model = self._resolve_model(backend)

        with open(still_path, "rb") as fh:
            image = types.Image(image_bytes=fh.read(), mime_type="image/png")
        # Gemini 레인은 길이·해상도를 전용 env로 오버라이드할 수 있다(없으면 공통 규칙).
        if backend == "gemini":
            duration = int(
                os.environ.get("GEMINI_VEO_DURATION_SECONDS") or _veo_seconds(duration_sec)
            )
            resolution = os.environ.get("GEMINI_VEO_RESOLUTION") or (
                "1080p" if width >= 1080 else "720p"
            )
        else:
            duration = _veo_seconds(duration_sec)
            resolution = "1080p" if width >= 1080 else "720p"
        # GCS 출력은 Vertex 레인에서만 붙인다(Gemini Developer API는 지원하지 않아 None으로 둔다).
        config = types.GenerateVideosConfig(
            aspect_ratio="9:16",
            number_of_videos=1,
            duration_seconds=duration,
            resolution=resolution,
            # 기본 나레이션(voiceover)은 별도 TTS라 오디오를 끈다. 온카메라 발화(integrated)
            # 일 때만 영상 모델이 립싱크 음성을 직접 낸다([ADR.md] ADR-0012).
            generate_audio=generate_audio,
            # 인물(성인) 생성을 허용해야 캐릭터 image-to-video가 RAI 필터에 안 막힌다.
            person_generation="allow_adult",
            output_gcs_uri=self.gcs_uri if backend == "vertex" else None,
        )

        # 원인-우선(cause-first) 재시도. 같은 run 안에선 스틸이 고정이라 원본 재시도는 결정론적
        # 으로 또 막혀 무의미하다. 그래서 블라인드 반복 대신 원인을 먼저 가린다:
        #  1) 원본 프롬프트로 시도. 성공이면 끝.
        #  2) RAI 빈 결과 -> 최소 중립 프롬프트로 진단 probe(같은 이미지).
        #     - probe 성공 = 원인은 '프롬프트' -> 방향 살린 LLM 재작성으로 복원(실패 시 probe 결과 사용).
        #     - probe 실패 = 원인은 '입력 이미지' -> 프롬프트 완화는 무의미 -> 예외로 스틸 폴백.
        # (일시적 오류는 _generate_video 안에서 tenacity가 백오프 재시도한다.)
        video = self._generate_video(client, prompt, image, config)
        if not video:
            print(
                "[veo] RAI 빈 결과 -> 원인 진단: 최소 중립 프롬프트 probe(같은 이미지)",
                file=sys.stderr,
            )
            probe_video = self._generate_video(client, _MINIMAL_PROMPT, image, config)
            if not probe_video:
                # 무해한 프롬프트로도 막힘 = 입력 이미지가 트리거. 프롬프트로는 못 뚫는다.
                # 대개 생성 인물이 실존 인물과 유사한 경우다. 스틸 폴백으로 덮지 않고 거절시킨다.
                raise VeoImageRAIError(
                    "입력 스틸이 콘텐츠 안전(RAI) 필터에 차단되었습니다(최소 중립 프롬프트로도 "
                    "실패, 프롬프트 무관). 생성된 인물이 실존·식별 가능한 인물과 너무 유사하거나 "
                    "기타 정책 사유일 수 있습니다."
                )
            print(
                "[veo] 원인=프롬프트(최소 프롬프트는 통과) -> LLM 재작성으로 방향 복원 시도",
                file=sys.stderr,
            )
            video = self._generate_video(client, self._rewrite_prompt(prompt), image, config)
            if not video:
                video = probe_video  # 재작성도 막히면 통과 확인된 최소 프롬프트 결과를 쓴다

        raw = str(Path(out_path).with_suffix(".veo.mp4"))
        if backend == "vertex":
            _download_gcs(video.uri, raw)
        else:
            # Gemini Developer API: File API로 바이트를 내려받아 로컬에 저장한다(GCS 미사용).
            client.files.download(file=video)
            video.save(raw)

        # 패널 길이로 자르고 목표 해상도/프레임레이트로 맞춘다.
        vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        cmd = ["ffmpeg", "-y", "-i", raw]
        if not generate_audio:
            # 기본(비발화)은 네이티브 오디오를 버리되 무음 트랙을 붙인다. 모든 클립이 오디오를
            # 갖게 해(ken_burns와 통일) concat·경계 크로스페이드에서 오디오 유무가 섞이지 않게 한다.
            cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        cmd += ["-t", f"{duration_sec:.3f}", "-vf", vf, "-r", str(fps)]
        if generate_audio:
            cmd += ["-c:a", "aac"]  # integrated 발화: 네이티브 립싱크 음성 보존
        else:
            cmd += ["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-shortest"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", out_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return out_path
