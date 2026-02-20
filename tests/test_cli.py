"""Tests for the CLI module."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from otterai.cli import main
from otterai import config


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory for testing."""
    # Clear any env vars that might interfere with config file tests
    env_patch = {"OTTERAI_USERNAME": "", "OTTERAI_PASSWORD": ""}
    with patch.dict(os.environ, env_patch, clear=False):
        # Remove the keys entirely if they exist
        os.environ.pop("OTTERAI_USERNAME", None)
        os.environ.pop("OTTERAI_PASSWORD", None)
        with patch.object(config, "CONFIG_DIR", tmp_path):
            with patch.object(config, "CONFIG_FILE", tmp_path / "config.json"):
                yield tmp_path


# =============================================================================
# Basic CLI Tests
# =============================================================================


def test_cli_help(runner):
    """Test that --help works."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "OtterAI CLI" in result.output


def test_cli_version(runner):
    """Test that --version works."""
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_speeches_help(runner):
    """Test speeches subcommand help."""
    result = runner.invoke(main, ["speeches", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "download" in result.output
    assert "upload" in result.output


def test_speakers_help(runner):
    """Test speakers subcommand help."""
    result = runner.invoke(main, ["speakers", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "create" in result.output


# =============================================================================
# Config Module Tests
# =============================================================================


def test_save_and_load_credentials(temp_config_dir):
    """Test saving and loading credentials."""
    config.save_credentials("testuser", "testpass")

    username, password = config.load_credentials()
    assert username == "testuser"
    assert password == "testpass"


def test_load_credentials_from_env(temp_config_dir):
    """Test that environment variables take precedence."""
    # Save credentials to file
    config.save_credentials("fileuser", "filepass")

    # Set env vars
    with patch.dict(os.environ, {"OTTERAI_USERNAME": "envuser", "OTTERAI_PASSWORD": "envpass"}):
        username, password = config.load_credentials()
        assert username == "envuser"
        assert password == "envpass"


def test_load_credentials_no_config(temp_config_dir):
    """Test loading credentials when no config exists."""
    username, password = config.load_credentials()
    assert username is None
    assert password is None


def test_clear_credentials(temp_config_dir):
    """Test clearing credentials."""
    config.save_credentials("testuser", "testpass")
    assert config.clear_credentials() is True
    assert not config.CONFIG_FILE.exists()


def test_clear_credentials_no_config(temp_config_dir):
    """Test clearing credentials when no config exists."""
    assert config.clear_credentials() is False


# =============================================================================
# Config Command Tests
# =============================================================================


def test_config_show_not_logged_in(runner, temp_config_dir):
    """Test config show when not logged in."""
    result = runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0
    assert "Not logged in" in result.output


def test_config_show_logged_in(runner, temp_config_dir):
    """Test config show when logged in."""
    config.save_credentials("testuser@example.com", "testpass")

    result = runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0
    assert "testuser@example.com" in result.output


def test_config_clear(runner, temp_config_dir):
    """Test config clear command."""
    config.save_credentials("testuser", "testpass")

    result = runner.invoke(main, ["config", "clear"])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()


# =============================================================================
# Login/Logout Tests (with mocked API)
# =============================================================================


def test_login_success(runner, temp_config_dir):
    """Test successful login."""
    mock_client = MagicMock()
    mock_client.login.return_value = {
        "status": 200,
        "data": {"email": "test@example.com", "userid": "123"}
    }

    with patch("otterai.cli.OtterAI", return_value=mock_client):
        result = runner.invoke(main, ["login"], input="test@example.com\ntestpass\n")

    assert result.exit_code == 0
    assert "Logged in" in result.output


def test_login_failure(runner, temp_config_dir):
    """Test failed login."""
    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 401, "data": {"error": "Invalid credentials"}}

    with patch("otterai.cli.OtterAI", return_value=mock_client):
        result = runner.invoke(main, ["login"], input="test@example.com\nbadpass\n")

    assert result.exit_code == 1


def test_logout(runner, temp_config_dir):
    """Test logout command."""
    config.save_credentials("testuser", "testpass")

    result = runner.invoke(main, ["logout"])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()


# =============================================================================
# Speeches Command Tests (with mocked API)
# =============================================================================


def test_speeches_list_not_logged_in(runner, temp_config_dir):
    """Test speeches list when not logged in."""
    result = runner.invoke(main, ["speeches", "list"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_speeches_list_success(runner, temp_config_dir):
    """Test successful speeches list."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.get_speeches.return_value = {
        "status": 200,
        "data": {
            "speeches": [
                {"otid": "abc123", "title": "Test Speech", "created_at": "2024-01-01"},
                {"otid": "def456", "title": "Another Speech", "created_at": "2024-01-02"}
            ]
        }
    }

    with patch("otterai.cli.OtterAI", return_value=mock_client):
        result = runner.invoke(main, ["speeches", "list"])

    assert result.exit_code == 0
    assert "Test Speech" in result.output
    assert "abc123" in result.output


def test_speeches_list_json_output(runner, temp_config_dir):
    """Test speeches list with JSON output."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.get_speeches.return_value = {
        "status": 200,
        "data": {"speeches": [{"otid": "abc123", "title": "Test"}]}
    }

    with patch("otterai.cli.OtterAI", return_value=mock_client):
        result = runner.invoke(main, ["speeches", "list", "--json"])

    assert result.exit_code == 0
    # Should be valid JSON
    data = json.loads(result.output)
    assert "speeches" in data


# =============================================================================
# Speakers Command Tests (with mocked API)
# =============================================================================


def test_speakers_list_success(runner, temp_config_dir):
    """Test successful speakers list."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.get_speakers.return_value = {
        "status": 200,
        "data": {
            "speakers": [
                {"speaker_id": "s1", "speaker_name": "John Doe"},
                {"speaker_id": "s2", "speaker_name": "Jane Smith"}
            ]
        }
    }

    with patch("otterai.cli.OtterAI", return_value=mock_client):
        result = runner.invoke(main, ["speakers", "list"])

    assert result.exit_code == 0
    assert "John Doe" in result.output
    assert "Jane Smith" in result.output


def test_speakers_tag_list_segments(runner, temp_config_dir):
    """Test speakers tag in list segments mode (no --transcript-uuid or --all)."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.get_speakers.return_value = {
        "status": 200,
        "data": {
            "speakers": [
                {"speaker_id": "s1", "speaker_name": "John Doe"}
            ]
        }
    }
    mock_client.get_speech.return_value = {
        "status": 200,
        "data": {
            "speech": {
                "transcripts": [
                    {"uuid": "uuid-001", "speaker_name": "John Doe", "transcript": "Hello world segment text"},
                    {"uuid": "uuid-002", "speaker_name": "Untagged", "transcript": "Another segment text here"}
                ]
            }
        }
    }

    with patch("otterai.cli.OtterAI", return_value=mock_client):
        result = runner.invoke(main, ["speakers", "tag", "speech123", "s1"])

    assert result.exit_code == 0
    assert "uuid-001" in result.output
    assert "uuid-002" in result.output
    assert "Available transcript segments" in result.output


# =============================================================================
# Folders Command Tests (with mocked API)
# =============================================================================


def test_folders_list_success(runner, temp_config_dir):
    """Test successful folders list."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.get_folders.return_value = {
        "status": 200,
        "data": {
            "folders": [
                {"id": "f1", "folder_name": "Work", "speech_count": 5},
                {"id": "f2", "folder_name": "Personal", "speech_count": 3}
            ]
        }
    }

    with patch("otterai.cli.OtterAI", return_value=mock_client):
        result = runner.invoke(main, ["folders", "list"])

    assert result.exit_code == 0
    assert "Work" in result.output
    assert "Personal" in result.output


def test_folders_create_success(runner, temp_config_dir):
    """Test successful folder creation."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.create_folder.return_value = {
        "status": 200,
        "data": {
            "folder": {"id": "f_new", "folder_name": "New Folder"}
        }
    }

    with patch("otterai.cli.OtterAI", return_value=mock_client):
        result = runner.invoke(main, ["folders", "create", "New Folder"])

    assert result.exit_code == 0
    assert "Created folder" in result.output
    assert "New Folder" in result.output


# =============================================================================
# Groups Command Tests (with mocked API)
# =============================================================================


def test_groups_list_success(runner, temp_config_dir):
    """Test successful groups list."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.list_groups.return_value = {
        "status": 200,
        "data": [
            {"id": "g1", "name": "Engineering"},
            {"id": "g2", "name": "Marketing"}
        ]
    }

    with patch("otterai.cli.OtterAI", return_value=mock_client):
        result = runner.invoke(main, ["groups", "list"])

    assert result.exit_code == 0
    assert "Engineering" in result.output
    assert "Marketing" in result.output
