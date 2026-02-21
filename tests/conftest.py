import pytest
import responses
from click.testing import CliRunner

import keyring
import keyring.errors

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
def saved_credentials(temp_config_dir, fake_keyring):
    """Save test credentials in the temp config dir (via keyring)."""
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


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch):
    """Replace keyring functions with a dict-backed implementation.

    Applied autouse so tests never touch the real system keyring.
    """
    store = {}

    def set_password(service, key, value):
        store[(service, key)] = value

    def get_password(service, key):
        return store.get((service, key))

    def delete_password(service, key):
        if (service, key) not in store:
            raise keyring.errors.PasswordDeleteError("not found")
        del store[(service, key)]

    monkeypatch.setattr("keyring.set_password", set_password)
    monkeypatch.setattr("keyring.get_password", get_password)
    monkeypatch.setattr("keyring.delete_password", delete_password)
    return store


@pytest.fixture
def broken_keyring(monkeypatch):
    """Simulate a system with no keyring backend."""

    def raise_error(*args, **kwargs):
        raise keyring.errors.NoKeyringError("no backend")

    monkeypatch.setattr("keyring.set_password", raise_error)
    monkeypatch.setattr("keyring.get_password", raise_error)
    monkeypatch.setattr("keyring.delete_password", raise_error)


@pytest.fixture
def partial_keyring_write(monkeypatch):
    """Simulate keyring where only the first set_password succeeds."""
    store = {}
    call_count = 0

    def set_password(service, key, value):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise keyring.errors.NoKeyringError("write failed on second call")
        store[(service, key)] = value

    def get_password(service, key):
        return store.get((service, key))

    def delete_password(service, key):
        if (service, key) not in store:
            raise keyring.errors.PasswordDeleteError("not found")
        del store[(service, key)]

    monkeypatch.setattr("keyring.set_password", set_password)
    monkeypatch.setattr("keyring.get_password", get_password)
    monkeypatch.setattr("keyring.delete_password", delete_password)
    return store
