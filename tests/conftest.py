import pytest
import responses
from click.testing import CliRunner

from otterai import config

API_BASE = "https://otter.ai/forward/api/v1/"


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path, monkeypatch):
    """Point config to a temp directory — no mocks needed."""
    monkeypatch.setenv("OTTERAI_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("OTTERAI_USERNAME", raising=False)
    monkeypatch.delenv("OTTERAI_PASSWORD", raising=False)
    return tmp_path


@pytest.fixture
def saved_credentials(temp_config_dir):
    """Save test credentials in the temp config dir."""
    config.save_credentials("testuser", "testpass")
    return ("testuser", "testpass")


@pytest.fixture
def mock_api():
    """Activate responses to intercept all HTTP requests."""
    with responses.RequestsMock() as rsps:
        yield rsps


@pytest.fixture
def mock_login(mock_api):
    """Register a successful login response."""
    mock_api.get(
        API_BASE + "login",
        json={"userid": "u123", "email": "testuser@example.com"},
        status=200,
    )
    return mock_api


@pytest.fixture(autouse=True)
def no_backoff_sleep(monkeypatch):
    """Keep tests fast by stubbing retry sleep globally."""
    monkeypatch.setattr("otterai.client.time.sleep", lambda _: None)
