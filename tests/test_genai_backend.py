"""`select_backend`의 백엔드 선택 규칙 테스트.

순수 환경변수 기반 결정이라 외부 호출 없이 검증한다. Vertex 자격 우선,
GENAI_BACKEND 강제, 자격 부족 시 Gemini 폴백, 둘 다 없으면 None을 확인한다.
"""

import pytest

from reel_gen_agent.analysis.gemini_client import select_backend

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
