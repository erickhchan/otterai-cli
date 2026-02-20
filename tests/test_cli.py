"""Tests for the CLI module."""

import json
from unittest.mock import MagicMock, patch

from otterai.cli import main
from otterai import config


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


def test_folders_help(runner):
    """Test folders subcommand help."""
    result = runner.invoke(main, ["folders", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "create" in result.output
    assert "rename" in result.output


def test_groups_help(runner):
    """Test groups subcommand help."""
    result = runner.invoke(main, ["groups", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output


def test_config_help(runner):
    """Test config subcommand help."""
    result = runner.invoke(main, ["config", "--help"])
    assert result.exit_code == 0
    assert "show" in result.output
    assert "clear" in result.output


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
        "data": {"email": "test@example.com", "userid": "123"},
    }

    with patch("otterai.cli.auth.OtterAIClient", return_value=mock_client):
        result = runner.invoke(main, ["login"], input="test@example.com\ntestpass\n")

    assert result.exit_code == 0
    assert "Logged in" in result.output


def test_login_failure(runner, temp_config_dir):
    """Test failed login."""
    mock_client = MagicMock()
    mock_client.login.return_value = {
        "status": 401,
        "data": {"error": "Invalid credentials"},
    }

    with patch("otterai.cli.auth.OtterAIClient", return_value=mock_client):
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
                {
                    "otid": "abc123",
                    "title": "Test Speech",
                    "created_at": 1704067200,
                },
                {
                    "otid": "def456",
                    "title": "Another Speech",
                    "created_at": 1704153600,
                },
            ]
        },
    }

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
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
        "data": {"speeches": [{"otid": "abc123", "title": "Test"}]},
    }

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
        result = runner.invoke(main, ["speeches", "list", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "speeches" in data


def test_speeches_get_success(runner, temp_config_dir):
    """Test successful speeches get."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.get_speech.return_value = {
        "status": 200,
        "data": {
            "speech": {
                "title": "My Speech",
                "otid": "abc123",
                "created_at": 0,
                "duration": 120,
            }
        },
    }

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
        result = runner.invoke(main, ["speeches", "get", "abc123"])

    assert result.exit_code == 0
    assert "My Speech" in result.output


def test_speeches_rename_success(runner, temp_config_dir):
    """Test successful speech rename."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.set_speech_title.return_value = {"status": 200, "data": {}}

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
        result = runner.invoke(main, ["speeches", "rename", "abc123", "New Title"])

    assert result.exit_code == 0
    assert "Renamed" in result.output


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
                {"speaker_id": "s2", "speaker_name": "Jane Smith"},
            ]
        },
    }

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
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
        "data": {"speakers": [{"speaker_id": "s1", "speaker_name": "John Doe"}]},
    }
    mock_client.get_speech.return_value = {
        "status": 200,
        "data": {
            "speech": {
                "transcripts": [
                    {
                        "uuid": "uuid-001",
                        "speaker_name": "John Doe",
                        "transcript": "Hello world segment text",
                    },
                    {
                        "uuid": "uuid-002",
                        "speaker_name": "Untagged",
                        "transcript": "Another segment text here",
                    },
                ]
            }
        },
    }

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
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
                {"id": "f2", "folder_name": "Personal", "speech_count": 3},
            ]
        },
    }

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
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
        "data": {"folder": {"id": "f_new", "folder_name": "New Folder"}},
    }

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
        result = runner.invoke(main, ["folders", "create", "New Folder"])

    assert result.exit_code == 0
    assert "Created folder" in result.output
    assert "New Folder" in result.output


def test_folders_rename_success(runner, temp_config_dir):
    """Test successful folder rename."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.rename_folder.return_value = {"status": 200, "data": {}}

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
        result = runner.invoke(main, ["folders", "rename", "f1", "Renamed"])

    assert result.exit_code == 0
    assert "Renamed" in result.output


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
            {"id": "g2", "name": "Marketing"},
        ],
    }

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
        result = runner.invoke(main, ["groups", "list"])

    assert result.exit_code == 0
    assert "Engineering" in result.output
    assert "Marketing" in result.output


# =============================================================================
# User Command Tests (with mocked API)
# =============================================================================


def test_user_success(runner, temp_config_dir):
    """Test successful user command."""
    config.save_credentials("testuser", "testpass")

    mock_client = MagicMock()
    mock_client.login.return_value = {"status": 200, "data": {}}
    mock_client.get_user.return_value = {
        "status": 200,
        "data": {"user": {"email": "test@example.com"}},
    }

    with patch("otterai.cli.helpers.OtterAIClient", return_value=mock_client):
        result = runner.invoke(main, ["user"])

    assert result.exit_code == 0
    assert "test@example.com" in result.output
