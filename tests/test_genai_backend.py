"""`select_backend`의 백엔드 선택 규칙과 `run_multimodal` 경로 라우팅 테스트.

select_backend는 순수 환경변수 기반 결정이라 외부 호출 없이 검증한다. Vertex 자격
우선, GENAI_BACKEND 강제, 자격 부족 시 Gemini 폴백, 둘 다 없으면 None을 확인한다.
run_multimodal은 외부 genai 호출을 모두 가짜로 바꿔, Vertex에서는 File API 업로드를
건너뛰고 키프레임으로 가는지(이전 회귀 버그)와 업로드 실패가 폴백으로 흘러가는지 본다.
"""

import pytest
from pydantic import BaseModel

from reel_gen_agent.analysis import gemini_client
from reel_gen_agent.analysis.gemini_client import run_multimodal, select_backend

# select_backend가 읽는 모든 환경변수. 각 테스트는 이 키들을 비운 상태에서 시작한다.
_ENV_KEYS = (
    "GENAI_BACKEND",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_ACCESS_TOKEN",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch):
    """관련 환경변수를 모두 지운 상태로 테스트를 시작한다(테스트 독립성)."""
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_auto_prefers_vertex_when_credentials_present(clean_env):
    """auto(기본)는 Vertex 자격이 갖춰지면 Vertex를 고른다."""
    clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    clean_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/abs/sa.json")
    clean_env.setenv("GEMINI_API_KEY", "k")  # 둘 다 있어도 Vertex 우선

    backend, params = select_backend()

    assert backend == "vertex"
    assert params == {"project": "my-project", "location": "global"}


def test_auto_uses_custom_location(clean_env):
    """Vertex 선택 시 GOOGLE_CLOUD_LOCATION을 반영한다."""
    clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    clean_env.setenv("GOOGLE_CLOUD_ACCESS_TOKEN", "tok")  # 토큰도 ADC 자격으로 인정
    clean_env.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    backend, params = select_backend()

    assert backend == "vertex"
    assert params["location"] == "us-central1"


def test_auto_falls_back_to_gemini_without_credentials(clean_env):
    """Vertex 자격이 없고 GEMINI_API_KEY만 있으면 Gemini로 내려간다."""
    clean_env.setenv("GEMINI_API_KEY", "gem-key")

    backend, params = select_backend()

    assert backend == "gemini"
    assert params == {"api_key": "gem-key"}


def test_project_without_adc_is_not_vertex(clean_env):
    """프로젝트만 있고 자격 파일/토큰이 없으면 Vertex로 보지 않는다."""
    clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    clean_env.setenv("GEMINI_API_KEY", "gem-key")

    backend, _ = select_backend()

    assert backend == "gemini"


def test_explicit_gemini_overrides_vertex_credentials(clean_env):
    """GENAI_BACKEND=gemini는 Vertex 자격이 있어도 Gemini를 강제한다."""
    clean_env.setenv("GENAI_BACKEND", "gemini")
    clean_env.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    clean_env.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/abs/sa.json")
    clean_env.setenv("GEMINI_API_KEY", "gem-key")

    backend, params = select_backend()

    assert backend == "gemini"
    assert params == {"api_key": "gem-key"}


def test_explicit_vertex_without_credentials_falls_back(clean_env):
    """GENAI_BACKEND=vertex라도 자격이 없으면 Gemini 키로 폴백한다."""
    clean_env.setenv("GENAI_BACKEND", "vertex")
    clean_env.setenv("GEMINI_API_KEY", "gem-key")

    backend, _ = select_backend()

    assert backend == "gemini"


def test_no_credentials_returns_none(clean_env):
    """Vertex 자격도 Gemini 키도 없으면 None(멀티모달 건너뜀)."""
    assert select_backend() is None


def test_api_key_override_is_used_for_gemini(clean_env):
    """인자로 넘긴 api_key가 환경변수보다 우선해 Gemini 키로 쓰인다."""
    clean_env.setenv("GEMINI_API_KEY", "env-key")

    backend, params = select_backend(api_key_override="arg-key")

    assert backend == "gemini"
    assert params == {"api_key": "arg-key"}


def test_google_api_key_is_accepted_as_gemini_key(clean_env):
    """GEMINI_API_KEY가 없을 때 GOOGLE_API_KEY를 Gemini 키로 받아들인다."""
    clean_env.setenv("GOOGLE_API_KEY", "google-key")

    backend, params = select_backend()

    assert backend == "gemini"
    assert params == {"api_key": "google-key"}


# --- run_multimodal 경로 라우팅 -------------------------------------------------


class _Desc(BaseModel):
    """run_multimodal 테스트용 최소 스키마."""

    ok: bool = True


@pytest.fixture
def fake_genai(clean_env, monkeypatch):
    """genai 외부 호출을 전부 가짜로 바꾸고, 어떤 경로를 탔는지 기록한다.

    whole(통째 입력)와 frames(키프레임)가 각각 불렸는지 calls로 본다.
    generate_structured는 받은 contents를 기록하고 항상 성공(_Desc)을 돌려준다.
    각 테스트는 whole_video_part를 성공/실패로 바꿔 경로를 결정한다.
    """
    calls = {"whole": 0, "frames": 0, "contents": []}

    monkeypatch.setattr(gemini_client, "make_client", lambda selection: object())

    def fake_generate(client, types, model, contents, schema):
        calls["contents"].append(contents)
        return schema()

    monkeypatch.setattr(gemini_client, "generate_structured", fake_generate)

    def fake_frames(path, types):
        calls["frames"] += 1
        return ["frame"]

    monkeypatch.setattr(gemini_client, "frame_parts", fake_frames)
    return calls


def test_short_video_uses_whole_input_not_keyframes(fake_genai, monkeypatch):
    """짧은 영상은 통째 입력(오디오+모션)이 성공하면 키프레임을 타지 않는다."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "p")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/abs/sa.json")  # vertex 선택

    def ok_whole(client, types, backend, path, tmp_dir):
        fake_genai["whole"] += 1
        return object()

    monkeypatch.setattr(gemini_client, "whole_video_part", ok_whole)

    result = run_multimodal("v.mp4", 10.0, _Desc, "vp", "fp")

    assert isinstance(result, _Desc)
    assert fake_genai["whole"] == 1
    assert fake_genai["frames"] == 0


def test_whole_input_failure_falls_back_to_keyframes(fake_genai, monkeypatch):
    """통째 입력이 실패해도 바깥 except로 빠지지 않고 키프레임으로 폴백한다(회귀)."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "p")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/abs/sa.json")

    def failing_whole(client, types, backend, path, tmp_dir):
        fake_genai["whole"] += 1
        raise RuntimeError("input kaboom")

    monkeypatch.setattr(gemini_client, "whole_video_part", failing_whole)

    result = run_multimodal("v.mp4", 10.0, _Desc, "vp", "fp")

    assert isinstance(result, _Desc)
    assert fake_genai["whole"] == 1  # 시도는 했고
    assert fake_genai["frames"] == 1  # 폴백까지 도달했다


def test_long_video_skips_whole_input(fake_genai, monkeypatch):
    """길이 상한을 넘는 영상은 통째 입력을 건너뛰고 바로 키프레임으로 간다."""
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    def boom(client, types, backend, path, tmp_dir):
        raise AssertionError("긴 영상에서 whole_video_part가 호출되면 안 됨")

    monkeypatch.setattr(gemini_client, "whole_video_part", boom)

    result = run_multimodal("v.mp4", 999.0, _Desc, "vp", "fp")

    assert isinstance(result, _Desc)
    assert fake_genai["whole"] == 0
    assert fake_genai["frames"] == 1


# --- whole_video_part: 백엔드별 영상 입력 방식 ----------------------------------


def test_whole_video_part_gemini_uses_file_api(monkeypatch, tmp_path):
    """Gemini 백엔드는 File API 업로드 경로를 쓴다."""
    from google.genai import types

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x01\x02\x03")
    sentinel = object()

    def fake_upload(client, path):
        return sentinel

    monkeypatch.setattr(gemini_client, "upload_and_wait", fake_upload)

    part = gemini_client.whole_video_part(object(), types, "gemini", str(video), str(tmp_path))

    assert part is sentinel


def test_whole_video_part_vertex_uses_inline_bytes(monkeypatch, tmp_path):
    """Vertex 백엔드는 File API 없이 인라인 바이트 Part(오디오+모션 포함)를 만든다."""
    from google.genai import types

    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x01\x02\x03")

    def boom(client, path):
        raise AssertionError("Vertex에서 File API 업로드가 호출되면 안 됨")

    monkeypatch.setattr(gemini_client, "upload_and_wait", boom)

    part = gemini_client.whole_video_part(object(), types, "vertex", str(video), str(tmp_path))

    assert part.inline_data is not None
    assert part.inline_data.mime_type == "video/mp4"


def test_whole_video_part_vertex_oversize_raises(monkeypatch, tmp_path):
    """Vertex 인라인 한도를 넘는 영상은 RuntimeError로 키프레임 폴백을 유도한다."""
    from google.genai import types

    monkeypatch.setattr(gemini_client, "VERTEX_INLINE_MAX_BYTES", 2)
    video = tmp_path / "big.mp4"
    video.write_bytes(b"\x00\x01\x02\x03")  # 한도(2B)보다 큼

    with pytest.raises(RuntimeError):
        gemini_client.whole_video_part(object(), types, "vertex", str(video), str(tmp_path))
