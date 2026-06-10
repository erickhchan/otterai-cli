"""Tests for the CLI module.

Uses the `responses` library for HTTP interception. No unittest.mock anywhere.
"""

import json
import os
import time

import responses
from click.testing import CliRunner

from otterai.cli import main
from otterai import config

API_BASE = "https://otter.ai/forward/api/v1/"


# =============================================================================
# Helper: register additional API responses on an rsps object
# =============================================================================


def _register_login(rsps):
    """Register a successful login response (for commands that don't use mock_login fixture)."""
    rsps.get(
        API_BASE + "login",
        json={"userid": "u123", "email": "testuser@example.com"},
        status=200,
    )


def _register_login_failure(rsps):
    """Register a failed login response."""
    rsps.get(
        API_BASE + "login",
        json={"error": "Invalid credentials"},
        status=401,
    )


# =============================================================================
# Basic CLI Tests (no API calls needed)
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
    assert "0.1.1" in result.output


def test_speeches_help(runner):
    """Test speeches subcommand help."""
    result = runner.invoke(main, ["speeches", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "get" in result.output
    assert "search" in result.output
    assert "rename" in result.output
    assert "download" in result.output
    assert "upload" in result.output
    assert "trash" in result.output
    assert "move" in result.output


def test_speakers_help(runner):
    """Test speakers subcommand help."""
    result = runner.invoke(main, ["speakers", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "create" in result.output
    assert "tag" in result.output


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
    assert "Config file:" in result.output
    assert "Backend: keyring" in result.output
    # Password should be masked
    assert "testpass" not in result.output
    assert "****" in result.output


def test_config_show_file_backend(runner, temp_config_dir, broken_keyring):
    """Test config show when credentials are in file (keyring unavailable)."""
    config.save_credentials("testuser@example.com", "testpass")
    result = runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0
    assert "Backend: file" in result.output


def test_config_show_env_backend(runner, temp_config_dir, monkeypatch):
    """Test config show when credentials come from environment variables."""
    monkeypatch.setenv("OTTERAI_USERNAME", "env-user")
    monkeypatch.setenv("OTTERAI_PASSWORD", "env-pass")
    result = runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0
    assert "Backend: environment" in result.output
    assert "env-user" in result.output


def test_config_show_config_path(runner, temp_config_dir):
    """Test config show displays config path even when not logged in."""
    result = runner.invoke(main, ["config", "show"])
    assert result.exit_code == 0
    assert "Config file:" in result.output


def test_config_clear_with_credentials(runner, temp_config_dir):
    """Test config clear when credentials exist."""
    config.save_credentials("testuser", "testpass")
    result = runner.invoke(main, ["config", "clear"])
    assert result.exit_code == 0
    assert "cleared" in result.output.lower()


def test_config_clear_without_credentials(runner, temp_config_dir):
    """Test config clear when no credentials exist."""
    result = runner.invoke(main, ["config", "clear"])
    assert result.exit_code == 0
    assert "No configuration found" in result.output


# =============================================================================
# Auth: Login Tests
# =============================================================================


def test_login_success(runner, temp_config_dir, mock_api):
    """Test successful login via prompts."""
    _register_login(mock_api)
    result = runner.invoke(
        main, ["login"], input="testuser@example.com\ntestpass\n"
    )
    assert result.exit_code == 0
    assert "Logged in as testuser@example.com" in result.output
    assert "Credentials saved to system keyring" in result.output
    # Verify credentials were actually saved
    username, password = config.load_credentials()
    assert username == "testuser@example.com"
    assert password == "testpass"


def test_login_success_file_fallback(runner, temp_config_dir, mock_api, broken_keyring):
    """Test successful login falls back to file when keyring unavailable."""
    _register_login(mock_api)
    result = runner.invoke(
        main, ["login"], input="testuser@example.com\ntestpass\n"
    )
    assert result.exit_code == 0
    assert "Credentials saved to" in result.output
    assert "system keyring" not in result.output


def test_login_with_options(runner, temp_config_dir, mock_api):
    """Test login with --username and --password options (no prompts)."""
    _register_login(mock_api)
    result = runner.invoke(
        main,
        ["login", "--username", "testuser@example.com", "--password", "testpass"],
    )
    assert result.exit_code == 0
    assert "Logged in as testuser@example.com" in result.output


def test_login_failure(runner, temp_config_dir, mock_api):
    """Test failed login exits with code 1."""
    _register_login_failure(mock_api)
    result = runner.invoke(
        main, ["login"], input="testuser@example.com\nbadpass\n"
    )
    assert result.exit_code == 1
    assert "Login failed" in result.output


# =============================================================================
# Auth: Logout Tests
# =============================================================================


def test_logout_with_credentials(runner, saved_credentials):
    """Test logout when credentials exist."""
    result = runner.invoke(main, ["logout"])
    assert result.exit_code == 0
    assert "Credentials cleared." in result.output
    # Verify credentials were actually removed
    username, password = config.load_credentials()
    assert username is None
    assert password is None


def test_logout_without_credentials(runner, temp_config_dir):
    """Test logout when no credentials exist."""
    result = runner.invoke(main, ["logout"])
    assert result.exit_code == 0
    assert "No saved credentials found." in result.output


# =============================================================================
# Auth: User Tests
# =============================================================================


def test_user_success(runner, saved_credentials, mock_login):
    """Test user command shows JSON user data."""
    mock_login.get(
        API_BASE + "user",
        json={"user": {"email": "testuser@example.com", "userid": "u123"}},
        status=200,
    )
    result = runner.invoke(main, ["user"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["user"]["email"] == "testuser@example.com"


def test_user_not_logged_in(runner, temp_config_dir):
    """Test user command when not logged in."""
    result = runner.invoke(main, ["user"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_user_api_failure(runner, saved_credentials, mock_login):
    """Test user command when API returns error."""
    mock_login.get(
        API_BASE + "user",
        json={"error": "unauthorized"},
        status=401,
    )
    result = runner.invoke(main, ["user"])
    assert result.exit_code == 1
    assert "Failed to get user" in result.output


# =============================================================================
# Speeches: List Tests
# =============================================================================


def test_speeches_list_not_logged_in(runner, temp_config_dir):
    """Test speeches list when not logged in."""
    result = runner.invoke(main, ["speeches", "list"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_speeches_list_success(runner, saved_credentials, mock_login):
    """Test successful speeches list shows formatted output."""
    mock_login.get(
        API_BASE + "speeches",
        json={
            "speeches": [
                {
                    "otid": "abc123",
                    "title": "Test Speech",
                    "created_at": 1704067200,
                    "duration": 300,
                    "live_status": "",
                    "folder": {"folder_name": "Work"},
                    "speakers": [{"speaker_name": "Alice"}],
                },
                {
                    "otid": "def456",
                    "title": "Another Speech",
                    "created_at": 1704153600,
                    "duration": 45,
                    "live_status": "live",
                    "folder": None,
                    "speakers": [],
                },
            ]
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "list"])
    assert result.exit_code == 0
    assert "Found 2 speeches" in result.output
    assert "abc123" in result.output
    assert "Test Speech" in result.output
    assert "def456" in result.output
    assert "Another Speech" in result.output
    assert "[LIVE]" in result.output
    assert "5m" in result.output
    assert "Work" in result.output
    assert "Alice" in result.output


def test_speeches_list_empty(runner, saved_credentials, mock_login):
    """Test speeches list when no speeches exist."""
    mock_login.get(
        API_BASE + "speeches",
        json={"speeches": []},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "list"])
    assert result.exit_code == 0
    assert "No speeches found." in result.output


def test_speeches_list_json(runner, saved_credentials, mock_login):
    """Test speeches list with --json flag."""
    mock_login.get(
        API_BASE + "speeches",
        json={"speeches": [{"otid": "abc123", "title": "Test"}]},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "speeches" in data
    assert data["speeches"][0]["otid"] == "abc123"


def test_speeches_list_with_folder_name(runner, saved_credentials, mock_login):
    """Test speeches list with --folder name resolves to folder ID."""
    mock_login.get(
        API_BASE + "folders",
        json={"folders": [{"id": 42, "folder_name": "Work"}]},
        status=200,
    )
    mock_login.get(
        API_BASE + "speeches",
        json={
            "speeches": [
                {
                    "otid": "s1",
                    "title": "In Work Folder",
                    "folder": {"id": 42, "folder_name": "Work"},
                },
                {
                    "otid": "s2",
                    "title": "In Personal Folder",
                    "folder": {"id": 99, "folder_name": "Personal"},
                },
            ]
        },
        status=200,
    )

    result = runner.invoke(main, ["speeches", "list", "--folder", "Work"])
    assert result.exit_code == 0
    assert "In Work Folder" in result.output
    assert "In Personal Folder" not in result.output

    speech_calls = [
        c for c in mock_login.calls if c.request.url.startswith(API_BASE + "speeches")
    ]
    assert speech_calls
    assert "folder=42" in speech_calls[0].request.url


def test_speeches_list_with_folder_id(runner, saved_credentials, mock_login):
    """Test speeches list with numeric --folder ID."""
    mock_login.get(
        API_BASE + "speeches",
        json={"speeches": [{"otid": "s1", "title": "In Folder 42"}]},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "list", "--folder", "42"])
    assert result.exit_code == 0
    assert "In Folder 42" in result.output


def test_speeches_list_with_folder_id_filters_mixed_results(
    runner, saved_credentials, mock_login
):
    """Test speeches list filters mixed-folder API results client-side."""
    mock_login.get(
        API_BASE + "speeches",
        json={
            "speeches": [
                {
                    "otid": "s1",
                    "title": "In Folder 42",
                    "folder": {"id": 42, "folder_name": "Work"},
                },
                {
                    "otid": "s2",
                    "title": "In Folder 99",
                    "folder": {"id": 99, "folder_name": "Other"},
                },
            ]
        },
        status=200,
    )

    result = runner.invoke(main, ["speeches", "list", "--folder", "42"])
    assert result.exit_code == 0
    assert "In Folder 42" in result.output
    assert "In Folder 99" not in result.output


def test_speeches_list_with_zero_padded_all_folder(runner, saved_credentials, mock_login):
    """Test --folder 000 behaves like folder 0 (all speeches)."""
    mock_login.get(
        API_BASE + "speeches",
        json={
            "speeches": [
                {
                    "otid": "s1",
                    "title": "Work Speech",
                    "folder": {"id": 42, "folder_name": "Work"},
                },
                {
                    "otid": "s2",
                    "title": "Other Speech",
                    "folder": {"id": 99, "folder_name": "Other"},
                },
            ]
        },
        status=200,
    )

    result = runner.invoke(main, ["speeches", "list", "--folder", "000"])
    assert result.exit_code == 0
    assert "Work Speech" in result.output
    assert "Other Speech" in result.output


def test_speeches_list_with_days_filter(runner, saved_credentials, mock_login):
    """Test speeches list with --days filter."""
    now = int(time.time())
    old_time = now - (10 * 86400)  # 10 days ago
    recent_time = now - (1 * 86400)  # 1 day ago

    mock_login.get(
        API_BASE + "speeches",
        json={
            "speeches": [
                {"otid": "recent", "title": "Recent", "created_at": recent_time},
                {"otid": "old", "title": "Old", "created_at": old_time},
            ]
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "list", "--days", "3"])
    assert result.exit_code == 0
    assert "Recent" in result.output
    assert "Old" not in result.output


def test_speeches_list_with_source(runner, saved_credentials, mock_login):
    """Test speeches list with --source filter."""
    mock_login.get(
        API_BASE + "speeches",
        json={"speeches": [{"otid": "s1", "title": "Shared One"}]},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "list", "--source", "shared"])
    assert result.exit_code == 0
    assert "Shared One" in result.output


def test_speeches_list_with_page_size(runner, saved_credentials, mock_login):
    """Test speeches list with --page-size option."""
    mock_login.get(
        API_BASE + "speeches",
        json={"speeches": [{"otid": "s1", "title": "First"}]},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "list", "--page-size", "10"])
    assert result.exit_code == 0
    assert "First" in result.output


def test_speeches_list_api_failure(runner, saved_credentials, mock_login):
    """Test speeches list when API returns error."""
    mock_login.get(
        API_BASE + "speeches",
        json={"error": "server error"},
        status=500,
    )
    result = runner.invoke(main, ["speeches", "list"])
    assert result.exit_code == 1
    assert "Failed to get speeches" in result.output


# =============================================================================
# Speeches: Get Tests
# =============================================================================


def test_speeches_get_success(runner, saved_credentials, mock_login):
    """Test successful speech get with formatted output."""
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "title": "My Meeting",
                "otid": "abc123",
                "created_at": 1704067200,
                "duration": 7200,
                "folder": {"folder_name": "Work", "id": "f1"},
                "speakers": [{"speaker_name": "Alice"}, {"speaker_name": "Bob"}],
                "transcripts": [
                    {
                        "speaker_name": "Alice",
                        "transcript": "Hello everyone",
                    },
                    {
                        "speaker_name": "Bob",
                        "transcript": "Hi Alice",
                    },
                ],
            }
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "get", "abc123"])
    assert result.exit_code == 0
    assert "Title: My Meeting" in result.output
    assert "ID (otid): abc123" in result.output
    assert "2h 0m" in result.output
    assert "Folder: Work" in result.output
    assert "Alice" in result.output
    assert "Bob" in result.output
    assert "Transcript:" in result.output
    assert "[Alice]: Hello everyone" in result.output
    assert "[Bob]: Hi Alice" in result.output


def test_speeches_get_resolves_speaker_ids(runner, saved_credentials, mock_login):
    """Test speech get resolves transcript speaker_id from speech speakers."""
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "title": "My Meeting",
                "otid": "abc123",
                "created_at": 0,
                "duration": 0,
                "speakers": [
                    {"id": 1, "speaker_name": "Alice"},
                    {"id": 2, "speaker_name": "Bob"},
                ],
                "transcripts": [
                    {"speaker_id": 1, "transcript": "Hello everyone"},
                    {"speaker_id": 2, "transcript": "Hi Alice"},
                    {
                        "speaker_id": 3,
                        "speaker_model_label": "3",
                        "transcript": "Fallback label",
                    },
                ],
            }
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "get", "abc123"])
    assert result.exit_code == 0
    assert "[Alice]: Hello everyone" in result.output
    assert "[Bob]: Hi Alice" in result.output
    assert "[3]: Fallback label" in result.output


def test_speeches_get_json(runner, saved_credentials, mock_login):
    """Test speech get with --json output."""
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "title": "My Meeting",
                "otid": "abc123",
                "created_at": 0,
                "duration": 0,
            }
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "get", "abc123", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["speech"]["title"] == "My Meeting"


def test_speeches_get_minimal(runner, saved_credentials, mock_login):
    """Test speech get with minimal data (no folder, no speakers, no transcripts)."""
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "title": "Untitled",
                "otid": "abc123",
                "created_at": 0,
                "duration": 0,
            }
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "get", "abc123"])
    assert result.exit_code == 0
    assert "Title: Untitled" in result.output
    # No folder or speakers lines when missing
    assert "Folder:" not in result.output


def test_speeches_get_api_failure(runner, saved_credentials, mock_login):
    """Test speech get when API returns error."""
    mock_login.get(
        API_BASE + "speech",
        json={"error": "not found"},
        status=404,
    )
    result = runner.invoke(main, ["speeches", "get", "nonexistent"])
    assert result.exit_code == 1
    assert "Failed to get speech" in result.output


# =============================================================================
# Speeches: Search Tests
# =============================================================================


def test_speeches_search_success(runner, saved_credentials, mock_login):
    """Test successful speech search."""
    mock_login.get(
        API_BASE + "advanced_search",
        json={
            "results": [
                {
                    "transcript": "This is a matching line",
                    "start_time": "00:01:30",
                    "end_time": "00:01:45",
                },
                {
                    "transcript": "Another match",
                    "start_time": "00:05:00",
                    "end_time": "00:05:10",
                },
            ]
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "search", "matching", "abc123"])
    assert result.exit_code == 0
    assert "[1]" in result.output
    assert "This is a matching line" in result.output
    assert "[2]" in result.output
    assert "Another match" in result.output


def test_speeches_search_no_results(runner, saved_credentials, mock_login):
    """Test speech search with no results.

    The or-chain `data.get("results") or data.get("matches") or data.get("items")`
    uses Python truthiness. An empty list [] is falsy, so only the LAST key in the
    chain can produce an empty list as the final value. We use "items" as the key.
    """
    mock_login.get(
        API_BASE + "advanced_search",
        json={"items": []},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "search", "nothing", "abc123"])
    assert result.exit_code == 0
    assert "No results found." in result.output


def test_speeches_search_empty_results_key(runner, saved_credentials, mock_login):
    """Test speech search when 'results' is empty list (falsy in or-chain).

    Because [] is falsy, data.get("results") returns [] which falls through the
    or-chain. With no other keys, matches becomes None, triggering json dump.
    """
    mock_login.get(
        API_BASE + "advanced_search",
        json={"results": []},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "search", "nothing", "abc123"])
    assert result.exit_code == 0
    # Falls through to json.dumps since matches ends up as None
    data = json.loads(result.output)
    assert data["results"] == []


def test_speeches_search_json(runner, saved_credentials, mock_login):
    """Test speech search with --json output."""
    mock_login.get(
        API_BASE + "advanced_search",
        json={
            "results": [{"transcript": "match", "start_time": "00:00:01"}]
        },
        status=200,
    )
    result = runner.invoke(
        main, ["speeches", "search", "match", "abc123", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "results" in data


def test_speeches_search_api_failure(runner, saved_credentials, mock_login):
    """Test speech search when API returns error."""
    mock_login.get(
        API_BASE + "advanced_search",
        json={"error": "bad request"},
        status=400,
    )
    result = runner.invoke(main, ["speeches", "search", "query", "abc123"])
    assert result.exit_code == 1
    assert "Search failed" in result.output


def test_speeches_search_fallback_data_keys(runner, saved_credentials, mock_login):
    """Test search handles 'matches' key (alternative response format)."""
    mock_login.get(
        API_BASE + "advanced_search",
        json={
            "matches": [
                {"text": "Found it", "start": "1:00", "end": "1:05"},
            ]
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "search", "it", "abc123"])
    assert result.exit_code == 0
    assert "Found it" in result.output


def test_speeches_search_no_known_keys(runner, saved_credentials, mock_login):
    """Test search with unrecognized response structure falls back to JSON dump."""
    mock_login.get(
        API_BASE + "advanced_search",
        json={"something_else": "value"},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "search", "q", "abc123"])
    assert result.exit_code == 0
    # Should fall back to json.dumps output
    assert "something_else" in result.output


# =============================================================================
# Speeches: Rename Tests
# =============================================================================


def test_speeches_rename_success(runner, saved_credentials, mock_login):
    """Test successful speech rename."""
    mock_login.get(
        API_BASE + "set_speech_title",
        json={"status": "ok"},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "rename", "abc123", "New Title"])
    assert result.exit_code == 0
    assert "Renamed speech abc123 to: New Title" in result.output


def test_speeches_rename_api_failure(runner, saved_credentials, mock_login):
    """Test speech rename when API returns error."""
    mock_login.get(
        API_BASE + "set_speech_title",
        json={"error": "not found"},
        status=404,
    )
    result = runner.invoke(main, ["speeches", "rename", "bad_id", "Title"])
    assert result.exit_code == 1
    assert "Rename failed" in result.output


# =============================================================================
# Speeches: Download Tests
# =============================================================================


def test_speeches_download_success(runner, saved_credentials, mock_login, tmp_path, monkeypatch):
    """Test successful speech download (single format)."""
    monkeypatch.chdir(tmp_path)
    mock_login.post(
        API_BASE + "bulk_export",
        body=b"file content here",
        status=200,
        content_type="application/octet-stream",
    )
    result = runner.invoke(main, ["speeches", "download", "abc123", "--format", "txt"])
    assert result.exit_code == 0
    assert "Downloaded: abc123.txt" in result.output
    assert (tmp_path / "abc123.txt").exists()


def test_speeches_download_with_name(runner, saved_credentials, mock_login, tmp_path, monkeypatch):
    """Test download with custom output filename."""
    monkeypatch.chdir(tmp_path)
    mock_login.post(
        API_BASE + "bulk_export",
        body=b"pdf content",
        status=200,
        content_type="application/octet-stream",
    )
    result = runner.invoke(
        main, ["speeches", "download", "abc123", "--format", "pdf", "--output", "myfile"]
    )
    assert result.exit_code == 0
    assert "Downloaded: myfile.pdf" in result.output
    assert (tmp_path / "myfile.pdf").exists()


def test_speeches_download_multi_format_zip(runner, saved_credentials, mock_login, tmp_path, monkeypatch):
    """Test download with multiple formats produces zip file."""
    monkeypatch.chdir(tmp_path)
    mock_login.post(
        API_BASE + "bulk_export",
        body=b"PK zip content",
        status=200,
        content_type="application/octet-stream",
    )
    result = runner.invoke(
        main, ["speeches", "download", "abc123", "--format", "txt,pdf"]
    )
    assert result.exit_code == 0
    assert "Downloaded: abc123.zip" in result.output
    assert (tmp_path / "abc123.zip").exists()


def test_speeches_download_api_failure(runner, saved_credentials, mock_login, tmp_path, monkeypatch):
    """Test download when API returns error."""
    monkeypatch.chdir(tmp_path)
    mock_login.post(
        API_BASE + "bulk_export",
        body=b"error",
        status=500,
        content_type="text/plain",
    )
    result = runner.invoke(main, ["speeches", "download", "abc123"])
    assert result.exit_code == 1


# =============================================================================
# Speeches: Upload Tests
# =============================================================================


def test_speeches_upload_success(runner, saved_credentials, mock_login, tmp_path):
    """Test successful speech upload."""
    # Create a real temp file to upload
    audio_file = tmp_path / "test_audio.mp4"
    audio_file.write_bytes(b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100)

    # Step 1: speech_upload_params
    mock_login.get(
        API_BASE + "speech_upload_params",
        json={
            "data": {
                "form_action": "https://s3.us-west-2.amazonaws.com/speech-upload-prod",
                "key": "uploads/test_key",
                "AWSAccessKeyId": "AKIA...",
                "policy": "base64policy",
                "signature": "sig123",
                "success_action_status": 201,
                "Content-Type": "audio/mp4",
            }
        },
        status=200,
    )
    # Step 2: OPTIONS preflight
    mock_login.add(
        responses.OPTIONS,
        "https://s3.us-west-2.amazonaws.com/speech-upload-prod",
        status=200,
    )
    # Step 3: S3 POST upload (returns XML)
    s3_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <PostResponse>
        <Location>https://s3.us-west-2.amazonaws.com/speech-upload-prod/uploads/test_key</Location>
        <Bucket>speech-upload-prod</Bucket>
        <Key>uploads/test_key</Key>
    </PostResponse>"""
    mock_login.post(
        "https://s3.us-west-2.amazonaws.com/speech-upload-prod",
        body=s3_xml,
        status=201,
        content_type="application/xml",
    )
    # Step 4: finish_speech_upload
    mock_login.get(
        API_BASE + "finish_speech_upload",
        json={"speech_id": "new_speech_123"},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "upload", str(audio_file)])
    assert result.exit_code == 0
    assert "Upload successful!" in result.output


def test_speeches_upload_file_not_found(runner, saved_credentials):
    """Test upload with nonexistent file."""
    result = runner.invoke(main, ["speeches", "upload", "/nonexistent/file.mp4"])
    assert result.exit_code != 0


# =============================================================================
# Speeches: Trash Tests
# =============================================================================


def test_speeches_trash_with_yes_flag(runner, saved_credentials, mock_login):
    """Test trashing a speech with --yes flag (skip confirmation)."""
    mock_login.post(
        API_BASE + "move_to_trash_bin",
        json={},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "trash", "abc123", "--yes"])
    assert result.exit_code == 0
    assert "Speech abc123 moved to trash." in result.output


def test_speeches_trash_without_yes_confirms(runner, saved_credentials, mock_login):
    """Test trashing a speech prompts for confirmation."""
    mock_login.post(
        API_BASE + "move_to_trash_bin",
        json={},
        status=200,
    )
    result = runner.invoke(main, ["speeches", "trash", "abc123"], input="y\n")
    assert result.exit_code == 0
    assert "Speech abc123 moved to trash." in result.output


def test_speeches_trash_without_yes_aborts(runner, saved_credentials):
    """Test trashing a speech aborts when user says no.

    No HTTP mocking needed because click.confirm aborts before any API call.
    """
    result = runner.invoke(main, ["speeches", "trash", "abc123"], input="n\n")
    assert result.exit_code == 1
    assert "Speech abc123 moved to trash." not in result.output


def test_speeches_trash_api_failure(runner, saved_credentials, mock_login):
    """Test trash when API returns error."""
    mock_login.post(
        API_BASE + "move_to_trash_bin",
        json={"error": "not found"},
        status=404,
    )
    result = runner.invoke(main, ["speeches", "trash", "bad_id", "--yes"])
    assert result.exit_code == 1
    assert "Failed to trash speech" in result.output


# =============================================================================
# Speeches: Move Tests
# =============================================================================


def test_speeches_move_with_folder_id(runner, saved_credentials, mock_login):
    """Test moving a speech with numeric folder ID."""
    mock_login.post(
        API_BASE + "add_folder_speeches",
        json={},
        status=200,
    )
    result = runner.invoke(
        main, ["speeches", "move", "abc123", "--folder", "42"]
    )
    assert result.exit_code == 0
    assert "Moved speech abc123 to folder 42" in result.output


def test_speeches_move_multiple(runner, saved_credentials, mock_login):
    """Test moving multiple speeches at once."""
    mock_login.post(
        API_BASE + "add_folder_speeches",
        json={},
        status=200,
    )
    result = runner.invoke(
        main, ["speeches", "move", "abc123", "def456", "--folder", "42"]
    )
    assert result.exit_code == 0
    assert "Moved 2 speeches to folder 42" in result.output


def test_speeches_move_with_folder_name(runner, saved_credentials, mock_login):
    """Test moving a speech with folder name resolution."""
    # Folder resolution via get_folders
    mock_login.get(
        API_BASE + "folders",
        json={
            "folders": [
                {"id": 42, "folder_name": "Work"},
                {"id": 99, "folder_name": "Personal"},
            ]
        },
        status=200,
    )
    mock_login.post(
        API_BASE + "add_folder_speeches",
        json={},
        status=200,
    )
    result = runner.invoke(
        main, ["speeches", "move", "abc123", "--folder", "Work"]
    )
    assert result.exit_code == 0
    assert "Moved speech abc123 to folder Work" in result.output


def test_speeches_move_folder_name_case_insensitive(runner, saved_credentials, mock_login):
    """Test folder name resolution is case-insensitive."""
    mock_login.get(
        API_BASE + "folders",
        json={"folders": [{"id": 42, "folder_name": "Work"}]},
        status=200,
    )
    mock_login.post(
        API_BASE + "add_folder_speeches",
        json={},
        status=200,
    )
    result = runner.invoke(
        main, ["speeches", "move", "abc123", "--folder", "work"]
    )
    assert result.exit_code == 0
    assert "Moved speech abc123 to folder work" in result.output


def test_speeches_move_folder_not_found(runner, saved_credentials, mock_login):
    """Test moving to non-existent folder name without --create."""
    mock_login.get(
        API_BASE + "folders",
        json={"folders": [{"id": 42, "folder_name": "Work"}]},
        status=200,
    )
    result = runner.invoke(
        main, ["speeches", "move", "abc123", "--folder", "NonExistent"]
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_speeches_move_create_folder(runner, saved_credentials, mock_login):
    """Test moving to non-existent folder with --create auto-creates it."""
    # First, get_folders returns no match
    mock_login.get(
        API_BASE + "folders",
        json={"folders": [{"id": 42, "folder_name": "Work"}]},
        status=200,
    )
    # Then create_folder
    mock_login.post(
        API_BASE + "create_folder",
        json={"folder": {"id": 99, "folder_name": "NewFolder"}},
        status=200,
    )
    # Then add_folder_speeches
    mock_login.post(
        API_BASE + "add_folder_speeches",
        json={},
        status=200,
    )
    result = runner.invoke(
        main,
        ["speeches", "move", "abc123", "--folder", "NewFolder", "--create"],
    )
    assert result.exit_code == 0
    assert "Created folder 'NewFolder'" in result.output
    assert "Moved speech abc123 to folder NewFolder" in result.output


def test_speeches_move_api_failure(runner, saved_credentials, mock_login):
    """Test move when API returns error."""
    mock_login.post(
        API_BASE + "add_folder_speeches",
        json={"error": "server error"},
        status=500,
    )
    result = runner.invoke(
        main, ["speeches", "move", "abc123", "--folder", "42"]
    )
    assert result.exit_code == 1
    assert "Failed to move speeches" in result.output


# =============================================================================
# Speakers: List Tests
# =============================================================================


def test_speakers_list_success(runner, saved_credentials, mock_login):
    """Test successful speakers list."""
    mock_login.get(
        API_BASE + "speakers",
        json={
            "speakers": [
                {"speaker_id": "s1", "speaker_name": "John Doe"},
                {"speaker_id": "s2", "speaker_name": "Jane Smith"},
            ]
        },
        status=200,
    )
    result = runner.invoke(main, ["speakers", "list"])
    assert result.exit_code == 0
    assert "Found 2 speakers" in result.output
    assert "John Doe" in result.output
    assert "Jane Smith" in result.output
    assert "s1" in result.output
    assert "s2" in result.output


def test_speakers_list_empty(runner, saved_credentials, mock_login):
    """Test speakers list when no speakers exist."""
    mock_login.get(
        API_BASE + "speakers",
        json={"speakers": []},
        status=200,
    )
    result = runner.invoke(main, ["speakers", "list"])
    assert result.exit_code == 0
    assert "No speakers found." in result.output


def test_speakers_list_json(runner, saved_credentials, mock_login):
    """Test speakers list with --json output."""
    mock_login.get(
        API_BASE + "speakers",
        json={
            "speakers": [{"speaker_id": "s1", "speaker_name": "John"}]
        },
        status=200,
    )
    result = runner.invoke(main, ["speakers", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "speakers" in data
    assert data["speakers"][0]["speaker_name"] == "John"


def test_speakers_list_api_failure(runner, saved_credentials, mock_login):
    """Test speakers list when API returns error."""
    mock_login.get(
        API_BASE + "speakers",
        json={"error": "unauthorized"},
        status=401,
    )
    result = runner.invoke(main, ["speakers", "list"])
    assert result.exit_code == 1
    assert "Failed to get speakers" in result.output


# =============================================================================
# Speakers: Create Tests
# =============================================================================


def test_speakers_create_success(runner, saved_credentials, mock_login):
    """Test successful speaker creation."""
    mock_login.post(
        API_BASE + "create_speaker",
        json={"speaker": {"id": "s_new", "speaker_name": "New Person"}},
        status=200,
    )
    result = runner.invoke(main, ["speakers", "create", "New Person"])
    assert result.exit_code == 0
    assert "Speaker 'New Person' created." in result.output


def test_speakers_create_api_failure(runner, saved_credentials, mock_login):
    """Test speaker creation when API returns error."""
    mock_login.post(
        API_BASE + "create_speaker",
        json={"error": "bad request"},
        status=400,
    )
    result = runner.invoke(main, ["speakers", "create", "BadName"])
    assert result.exit_code == 1
    assert "Failed to create speaker" in result.output


# =============================================================================
# Speakers: Tag Tests
# =============================================================================


def test_speakers_tag_list_segments(runner, saved_credentials, mock_login):
    """Test speakers tag without -t or --all lists transcript segments."""
    # get_speakers
    mock_login.get(
        API_BASE + "speakers",
        json={
            "speakers": [
                {"speaker_id": "s1", "speaker_name": "John Doe"},
            ]
        },
        status=200,
    )
    # get_speech
    mock_login.get(
        API_BASE + "speech",
        json={
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
        status=200,
    )
    result = runner.invoke(main, ["speakers", "tag", "speech123", "s1"])
    assert result.exit_code == 0
    assert "Available transcript segments" in result.output
    assert "uuid-001" in result.output
    assert "uuid-002" in result.output
    assert "John Doe" in result.output
    assert "Untagged" in result.output
    assert "Use -t <uuid>" in result.output


def test_speakers_tag_list_segments_json(runner, saved_credentials, mock_login):
    """Test speakers tag list segments with --json output."""
    mock_login.get(
        API_BASE + "speakers",
        json={
            "speakers": [{"speaker_id": "s1", "speaker_name": "Alice"}]
        },
        status=200,
    )
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "transcripts": [
                    {
                        "uuid": "uuid-001",
                        "speaker_id": "s0",
                        "speaker_name": "Untagged",
                        "transcript": "Some text here",
                    },
                ]
            }
        },
        status=200,
    )
    result = runner.invoke(
        main, ["speakers", "tag", "speech123", "s1", "--json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["uuid"] == "uuid-001"


def test_speakers_tag_specific_segment(runner, saved_credentials, mock_login):
    """Test tagging a specific transcript segment with -t."""
    mock_login.get(
        API_BASE + "speakers",
        json={
            "speakers": [{"speaker_id": "s1", "speaker_name": "Alice"}]
        },
        status=200,
    )
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "transcripts": [
                    {"uuid": "uuid-001", "speaker_name": "Untagged", "transcript": "Text"},
                ]
            }
        },
        status=200,
    )
    mock_login.get(
        API_BASE + "set_transcript_speaker",
        json={},
        status=200,
    )
    result = runner.invoke(
        main,
        ["speakers", "tag", "speech123", "s1", "-t", "uuid-001"],
    )
    assert result.exit_code == 0
    assert "Tagged segment uuid-001 as 'Alice'" in result.output


def test_speakers_tag_all_segments(runner, saved_credentials, mock_login):
    """Test tagging all transcript segments with --all."""
    mock_login.get(
        API_BASE + "speakers",
        json={
            "speakers": [{"speaker_id": "s1", "speaker_name": "Alice"}]
        },
        status=200,
    )
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "transcripts": [
                    {"uuid": "uuid-001", "speaker_name": "Untagged", "transcript": "First"},
                    {"uuid": "uuid-002", "speaker_name": "Untagged", "transcript": "Second"},
                    {"uuid": "uuid-003", "speaker_name": "Untagged", "transcript": "Third"},
                ]
            }
        },
        status=200,
    )
    # Register three set_transcript_speaker responses (one per segment)
    for _ in range(3):
        mock_login.get(
            API_BASE + "set_transcript_speaker",
            json={},
            status=200,
        )
    result = runner.invoke(
        main, ["speakers", "tag", "speech123", "s1", "--all"]
    )
    assert result.exit_code == 0
    assert "Tagged 3/3 segments as 'Alice'" in result.output


def test_speakers_tag_speaker_not_found(runner, saved_credentials, mock_login):
    """Test tagging with a speaker_id that doesn't exist."""
    mock_login.get(
        API_BASE + "speakers",
        json={"speakers": [{"speaker_id": "s1", "speaker_name": "Alice"}]},
        status=200,
    )
    result = runner.invoke(
        main, ["speakers", "tag", "speech123", "nonexistent"]
    )
    assert result.exit_code == 1
    assert "Speaker ID nonexistent not found" in result.output


def test_speakers_tag_all_partial_failure(runner, saved_credentials, mock_login):
    """Test tagging all segments when some fail."""
    mock_login.get(
        API_BASE + "speakers",
        json={"speakers": [{"speaker_id": "s1", "speaker_name": "Alice"}]},
        status=200,
    )
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "transcripts": [
                    {"uuid": "uuid-001", "speaker_name": "Untagged", "transcript": "First"},
                    {"uuid": "uuid-002", "speaker_name": "Untagged", "transcript": "Second"},
                ]
            }
        },
        status=200,
    )
    # First succeeds, second fails
    mock_login.get(
        API_BASE + "set_transcript_speaker",
        json={},
        status=200,
    )
    mock_login.get(
        API_BASE + "set_transcript_speaker",
        json={"error": "failed"},
        status=500,
    )
    result = runner.invoke(
        main, ["speakers", "tag", "speech123", "s1", "--all"]
    )
    assert result.exit_code == 0
    assert "Tagged 1/2 segments as 'Alice'" in result.output


# =============================================================================
# Folders: List Tests
# =============================================================================


def test_folders_list_success(runner, saved_credentials, mock_login):
    """Test successful folders list."""
    mock_login.get(
        API_BASE + "folders",
        json={
            "folders": [
                {"id": "f1", "folder_name": "Work", "speech_count": 5},
                {"id": "f2", "folder_name": "Personal", "speech_count": 3},
            ]
        },
        status=200,
    )
    result = runner.invoke(main, ["folders", "list"])
    assert result.exit_code == 0
    assert "Found 2 folders" in result.output
    assert "Work" in result.output
    assert "Personal" in result.output
    assert "5 speeches" in result.output
    assert "3 speeches" in result.output


def test_folders_list_empty(runner, saved_credentials, mock_login):
    """Test folders list when no folders exist."""
    mock_login.get(
        API_BASE + "folders",
        json={"folders": []},
        status=200,
    )
    result = runner.invoke(main, ["folders", "list"])
    assert result.exit_code == 0
    assert "No folders found." in result.output


def test_folders_list_json(runner, saved_credentials, mock_login):
    """Test folders list with --json output."""
    mock_login.get(
        API_BASE + "folders",
        json={
            "folders": [{"id": "f1", "folder_name": "Work", "speech_count": 5}]
        },
        status=200,
    )
    result = runner.invoke(main, ["folders", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "folders" in data
    assert data["folders"][0]["folder_name"] == "Work"


def test_folders_list_api_failure(runner, saved_credentials, mock_login):
    """Test folders list when API returns error."""
    mock_login.get(
        API_BASE + "folders",
        json={"error": "forbidden"},
        status=403,
    )
    result = runner.invoke(main, ["folders", "list"])
    assert result.exit_code == 1
    assert "Failed to get folders" in result.output


# =============================================================================
# Folders: Create Tests
# =============================================================================


def test_folders_create_success(runner, saved_credentials, mock_login):
    """Test successful folder creation."""
    mock_login.post(
        API_BASE + "create_folder",
        json={"folder": {"id": "f_new", "folder_name": "New Folder"}},
        status=200,
    )
    result = runner.invoke(main, ["folders", "create", "New Folder"])
    assert result.exit_code == 0
    assert "Created folder 'New Folder'" in result.output
    assert "f_new" in result.output


def test_folders_create_json(runner, saved_credentials, mock_login):
    """Test folder creation with --json output."""
    mock_login.post(
        API_BASE + "create_folder",
        json={"folder": {"id": "f_new", "folder_name": "New Folder"}},
        status=200,
    )
    result = runner.invoke(main, ["folders", "create", "New Folder", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["folder"]["id"] == "f_new"


def test_folders_create_api_failure(runner, saved_credentials, mock_login):
    """Test folder creation when API returns error."""
    mock_login.post(
        API_BASE + "create_folder",
        json={"error": "bad request"},
        status=400,
    )
    result = runner.invoke(main, ["folders", "create", "BadFolder"])
    assert result.exit_code == 1
    assert "Failed to create folder" in result.output


# =============================================================================
# Folders: Rename Tests
# =============================================================================


def test_folders_rename_success(runner, saved_credentials, mock_login):
    """Test successful folder rename."""
    mock_login.post(
        API_BASE + "rename_folder",
        json={},
        status=200,
    )
    result = runner.invoke(main, ["folders", "rename", "f1", "Renamed Folder"])
    assert result.exit_code == 0
    assert "Renamed folder f1 to 'Renamed Folder'" in result.output


def test_folders_rename_api_failure(runner, saved_credentials, mock_login):
    """Test folder rename when API returns error."""
    mock_login.post(
        API_BASE + "rename_folder",
        json={"error": "not found"},
        status=404,
    )
    result = runner.invoke(main, ["folders", "rename", "bad_id", "New Name"])
    assert result.exit_code == 1
    assert "Failed to rename folder" in result.output


# =============================================================================
# Groups: List Tests
# =============================================================================


def test_groups_list_success_as_list(runner, saved_credentials, mock_login):
    """Test successful groups list when API returns a list."""
    mock_login.get(
        API_BASE + "list_groups",
        json=[
            {"id": "g1", "name": "Engineering"},
            {"id": "g2", "name": "Marketing"},
        ],
        status=200,
    )
    result = runner.invoke(main, ["groups", "list"])
    assert result.exit_code == 0
    assert "Found 2 groups" in result.output
    assert "Engineering" in result.output
    assert "Marketing" in result.output
    assert "id: g1" in result.output
    assert "id: g2" in result.output


def test_groups_list_empty(runner, saved_credentials, mock_login):
    """Test groups list when no groups exist."""
    mock_login.get(
        API_BASE + "list_groups",
        json=[],
        status=200,
    )
    result = runner.invoke(main, ["groups", "list"])
    assert result.exit_code == 0
    assert "No groups found." in result.output


def test_groups_list_dict_response(runner, saved_credentials, mock_login):
    """Test groups list when API returns a dict (falls back to JSON dump)."""
    mock_login.get(
        API_BASE + "list_groups",
        json={"groups": [{"name": "Team A"}]},
        status=200,
    )
    result = runner.invoke(main, ["groups", "list"])
    assert result.exit_code == 0
    # When data is a dict, it falls back to json.dumps
    assert "groups" in result.output


def test_groups_list_json(runner, saved_credentials, mock_login):
    """Test groups list with --json output."""
    mock_login.get(
        API_BASE + "list_groups",
        json=[{"id": "g1", "name": "Engineering"}],
        status=200,
    )
    result = runner.invoke(main, ["groups", "list", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["name"] == "Engineering"


def test_groups_list_with_group_name_key(runner, saved_credentials, mock_login):
    """Test groups list with group_name key instead of name."""
    mock_login.get(
        API_BASE + "list_groups",
        json=[{"id": "g1", "group_name": "Design Team"}],
        status=200,
    )
    result = runner.invoke(main, ["groups", "list"])
    assert result.exit_code == 0
    assert "Design Team" in result.output


def test_groups_list_with_no_id(runner, saved_credentials, mock_login):
    """Test groups list where groups have no id field."""
    mock_login.get(
        API_BASE + "list_groups",
        json=[{"name": "Ad Hoc Group"}],
        status=200,
    )
    result = runner.invoke(main, ["groups", "list"])
    assert result.exit_code == 0
    assert "Ad Hoc Group" in result.output
    # Should not show "(id: ...)" when id is missing
    assert "id:" not in result.output


def test_groups_list_string_entries(runner, saved_credentials, mock_login):
    """Test groups list when entries are plain strings."""
    mock_login.get(
        API_BASE + "list_groups",
        json=["Group Alpha", "Group Beta"],
        status=200,
    )
    result = runner.invoke(main, ["groups", "list"])
    assert result.exit_code == 0
    assert "Group Alpha" in result.output
    assert "Group Beta" in result.output


def test_groups_list_api_failure(runner, saved_credentials, mock_login):
    """Test groups list when API returns error."""
    mock_login.get(
        API_BASE + "list_groups",
        json={"error": "unauthorized"},
        status=401,
    )
    result = runner.invoke(main, ["groups", "list"])
    assert result.exit_code == 1
    assert "Failed to get groups" in result.output


# =============================================================================
# Helpers: _format_timestamp Tests
# =============================================================================


def test_format_timestamp():
    """Test epoch timestamp formatting (US Eastern timezone)."""
    from otterai.cli.helpers import _format_timestamp

    # 1577886000 = Wed Jan 01, 2020 12:00:00 PM UTC = Wed Jan 01, 2020 07:00 AM ET
    result = _format_timestamp(1577886000)
    assert result  # Should produce a non-empty string
    assert "2020" in result
    assert "Jan" in result
    assert "Wed" in result


def test_format_timestamp_zero():
    """Test that 0 epoch returns empty string."""
    from otterai.cli.helpers import _format_timestamp

    assert _format_timestamp(0) == ""


def test_format_timestamp_none():
    """Test that None epoch returns empty string."""
    from otterai.cli.helpers import _format_timestamp

    assert _format_timestamp(None) == ""


# =============================================================================
# Helpers: _format_duration Tests
# =============================================================================


def test_format_duration_zero():
    """Test 0 seconds."""
    from otterai.cli.helpers import _format_duration

    assert _format_duration(0) == "0s"


def test_format_duration_seconds():
    """Test seconds only."""
    from otterai.cli.helpers import _format_duration

    assert _format_duration(45) == "45s"


def test_format_duration_minutes():
    """Test minutes."""
    from otterai.cli.helpers import _format_duration

    assert _format_duration(300) == "5m"


def test_format_duration_hours_and_minutes():
    """Test hours with remaining minutes."""
    from otterai.cli.helpers import _format_duration

    assert _format_duration(9000) == "2h 30m"


def test_format_duration_exact_hour():
    """Test exact hour."""
    from otterai.cli.helpers import _format_duration

    assert _format_duration(3600) == "1h 0m"


def test_format_duration_none():
    """Test None returns 0s."""
    from otterai.cli.helpers import _format_duration

    assert _format_duration(None) == "0s"


def test_format_duration_one_second():
    """Test 1 second."""
    from otterai.cli.helpers import _format_duration

    assert _format_duration(1) == "1s"


def test_format_duration_59_seconds():
    """Test just under a minute."""
    from otterai.cli.helpers import _format_duration

    assert _format_duration(59) == "59s"


def test_format_duration_60_seconds():
    """Test exactly one minute."""
    from otterai.cli.helpers import _format_duration

    assert _format_duration(60) == "1m"


# =============================================================================
# Helpers: format_speech_markdown Tests
# =============================================================================


def test_format_speech_markdown_full():
    """Test markdown formatting with all fields present."""
    from otterai.cli.helpers import format_speech_markdown

    data = {
        "speech": {
            "title": "Team Standup",
            "created_at": 1704067200,
            "start_time": 1704067200,
            "end_time": 1704069000,
            "duration": 1800,
            "summary": "Daily sync summary",
            "speech_id": "SPEECH123",
            "folder": {"folder_name": "Work", "id": "f1"},
            "speakers": [{"speaker_name": "Alice"}, {"speaker_name": "Bob"}],
            "transcripts": [
                {"speaker_name": "Alice", "transcript": "Good morning"},
                {"speaker_name": "Bob", "transcript": "Hey Alice"},
            ],
        }
    }
    result = format_speech_markdown(data)
    assert result.startswith("---\n")
    assert 'title: "Team Standup"' in result
    assert 'summary: "Daily sync summary"' in result
    assert 'start_time: "2024-01-01T00:00:00Z"' in result
    assert 'end_time: "2024-01-01T00:30:00Z"' in result
    assert "duration_seconds: 1800" in result
    assert 'source: "otter.ai"' in result
    assert 'speech_id: "SPEECH123"' in result
    assert 'folder: "Work"' in result
    assert 'folder_id: "f1"' in result
    assert "speakers:" in result
    assert '  - "Alice"' in result
    assert '  - "Bob"' in result
    assert "created_at:" not in result
    assert "otid:" not in result
    assert "# Team Standup" in result
    assert "## Transcript" in result
    assert "**Alice:** Good morning" in result
    assert "**Bob:** Hey Alice" in result


def test_format_speech_markdown_minimal():
    """Test markdown with missing/zero fields produces just a title."""
    from otterai.cli.helpers import format_speech_markdown

    data = {
        "speech": {
            "title": "Minimal",
            "created_at": 0,
            "duration": 0,
        }
    }
    result = format_speech_markdown(data)
    assert result.startswith("---\n")
    assert 'title: "Minimal"' in result
    assert "summary:" not in result
    assert "start_time:" not in result
    assert "end_time:" not in result
    assert "duration_seconds:" not in result
    assert 'source: "otter.ai"' in result
    assert "speech_id:" not in result
    assert "folder:" not in result
    assert "speakers:" not in result
    assert "# Minimal" in result


def test_format_speech_markdown_none_title():
    """Test markdown with None title defaults to Untitled."""
    from otterai.cli.helpers import format_speech_markdown

    data = {"speech": {"title": None, "created_at": 0, "duration": 0}}
    result = format_speech_markdown(data)
    assert 'title: "Untitled"' in result
    assert "# Untitled" in result


def test_format_speech_markdown_transcripts_at_top_level():
    """Test markdown when transcripts are at top-level data, not nested."""
    from otterai.cli.helpers import format_speech_markdown

    data = {
        "speech": {
            "title": "Top Level",
            "created_at": 0,
            "duration": 0,
        },
        "transcripts": [
            {"speaker_name": "Host", "transcript": "Welcome"},
        ],
    }
    result = format_speech_markdown(data)
    assert "## Transcript" in result
    assert "**Host:** Welcome" in result


def test_format_speech_markdown_custom_fields():
    """Test custom fields output includes only selected fields."""
    from otterai.cli.helpers import format_speech_markdown

    data = {
        "speech": {
            "title": "Custom",
            "summary": "Should not be included",
            "speech_id": "sp1",
            "transcripts": [{"transcript": "Hi"}],
        }
    }
    result = format_speech_markdown(
        data,
        frontmatter_fields=["speech_id", "title"],
    )
    assert 'speech_id: "sp1"' in result
    assert 'title: "Custom"' in result
    assert 'summary: "Should not be included"' not in result


def test_format_speech_markdown_invalid_field_raises():
    """Test invalid custom frontmatter field raises a clear error."""
    from otterai.cli.helpers import format_speech_markdown
    import pytest

    with pytest.raises(ValueError, match="Unknown frontmatter field"):
        format_speech_markdown({}, frontmatter_fields=["invalid_field"])


def test_format_speech_markdown_unknown_speaker():
    """Test markdown with missing speaker_name defaults to Unknown."""
    from otterai.cli.helpers import format_speech_markdown

    data = {
        "speech": {
            "title": "Test",
            "created_at": 0,
            "duration": 0,
            "transcripts": [
                {"transcript": "Some text"},
            ],
        }
    }
    result = format_speech_markdown(data)
    assert "**Unknown:** Some text" in result


def test_format_speech_markdown_resolves_speaker_ids():
    """Test markdown resolves transcript speaker_id from speech speakers."""
    from otterai.cli.helpers import format_speech_markdown

    data = {
        "speech": {
            "title": "Test",
            "created_at": 0,
            "duration": 0,
            "speakers": [
                {"id": 1, "speaker_name": "Alice"},
                {"id": 2, "speaker_name": "Bob"},
            ],
            "transcripts": [
                {"speaker_id": 1, "transcript": "Hello everyone"},
                {"speaker_id": 2, "transcript": "Hi Alice"},
                {
                    "speaker_id": 3,
                    "speaker_model_label": "3",
                    "transcript": "Fallback label",
                },
            ],
        }
    }
    result = format_speech_markdown(data)
    assert "**Alice:** Hello everyone" in result
    assert "**Bob:** Hi Alice" in result
    assert "**3:** Fallback label" in result


def test_format_speech_markdown_empty_transcripts():
    """Test markdown with empty transcripts list omits separator."""
    from otterai.cli.helpers import format_speech_markdown

    data = {
        "speech": {
            "title": "Empty",
            "created_at": 0,
            "duration": 0,
            "transcripts": [],
        }
    }
    result = format_speech_markdown(data)
    assert "## Transcript" not in result


def test_format_speech_markdown_empty_data():
    """Test markdown with completely empty data dict."""
    from otterai.cli.helpers import format_speech_markdown

    result = format_speech_markdown({})
    assert result.startswith("---\n")
    assert 'title: "Untitled"' in result
    assert "# Untitled" in result


def test_format_speech_markdown_empty_string_title():
    """Test markdown with empty string title defaults to Untitled."""
    from otterai.cli.helpers import format_speech_markdown

    data = {"speech": {"title": "", "created_at": 0, "duration": 0}}
    result = format_speech_markdown(data)
    assert 'title: "Untitled"' in result
    assert "# Untitled" in result


# =============================================================================
# Helpers: _resolve_folder_id Tests
# =============================================================================


def test_resolve_folder_id_numeric(saved_credentials, mock_login):
    """Test numeric folder reference is returned as-is."""
    from otterai.cli.helpers import _resolve_folder_id, get_authenticated_client

    client = get_authenticated_client()
    result = _resolve_folder_id(client, "42")
    assert result == "42"


def test_resolve_folder_id_by_name(saved_credentials, mock_login):
    """Test folder name is resolved to ID."""
    from otterai.cli.helpers import _resolve_folder_id, get_authenticated_client

    mock_login.get(
        API_BASE + "folders",
        json={
            "folders": [
                {"id": 42, "folder_name": "Work"},
                {"id": 99, "folder_name": "Personal"},
            ]
        },
        status=200,
    )
    client = get_authenticated_client()
    result = _resolve_folder_id(client, "Work")
    assert result == "42"


def test_resolve_folder_id_case_insensitive(saved_credentials, mock_login):
    """Test folder name resolution is case-insensitive."""
    from otterai.cli.helpers import _resolve_folder_id, get_authenticated_client
    import click
    import pytest

    mock_login.get(
        API_BASE + "folders",
        json={"folders": [{"id": 42, "folder_name": "Work"}]},
        status=200,
    )
    client = get_authenticated_client()
    result = _resolve_folder_id(client, "work")
    assert result == "42"


def test_resolve_folder_id_not_found(saved_credentials, mock_login):
    """Test folder name that does not exist raises ClickException."""
    from otterai.cli.helpers import _resolve_folder_id, get_authenticated_client
    import click
    import pytest

    mock_login.get(
        API_BASE + "folders",
        json={"folders": [{"id": 42, "folder_name": "Work"}]},
        status=200,
    )
    client = get_authenticated_client()
    with pytest.raises(click.ClickException, match="not found"):
        _resolve_folder_id(client, "NonExistent")


# =============================================================================
# Helpers: get_authenticated_client Tests
# =============================================================================


def test_get_authenticated_client_no_credentials(temp_config_dir):
    """Test get_authenticated_client raises when no credentials exist."""
    from otterai.cli.helpers import get_authenticated_client
    import click
    import pytest

    with pytest.raises(click.ClickException, match="Not logged in"):
        get_authenticated_client()


def test_get_authenticated_client_login_fails(saved_credentials, mock_api):
    """Test get_authenticated_client raises when login fails."""
    from otterai.cli.helpers import get_authenticated_client
    import click
    import pytest

    _register_login_failure(mock_api)
    with pytest.raises(click.ClickException, match="Login failed"):
        get_authenticated_client()


def test_get_authenticated_client_success(saved_credentials, mock_login):
    """Test get_authenticated_client returns a logged-in client."""
    from otterai.cli.helpers import get_authenticated_client

    client = get_authenticated_client()
    assert client._userid == "u123"


# =============================================================================
# Edge cases: not logged in for various commands
# =============================================================================


def test_speeches_get_not_logged_in(runner, temp_config_dir):
    """Test speeches get when not logged in."""
    result = runner.invoke(main, ["speeches", "get", "abc123"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_speeches_search_not_logged_in(runner, temp_config_dir):
    """Test speeches search when not logged in."""
    result = runner.invoke(main, ["speeches", "search", "query", "abc123"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_speeches_rename_not_logged_in(runner, temp_config_dir):
    """Test speeches rename when not logged in."""
    result = runner.invoke(main, ["speeches", "rename", "abc123", "Title"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_speeches_trash_not_logged_in(runner, temp_config_dir):
    """Test speeches trash when not logged in."""
    result = runner.invoke(main, ["speeches", "trash", "abc123", "--yes"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_speeches_move_not_logged_in(runner, temp_config_dir):
    """Test speeches move when not logged in."""
    result = runner.invoke(main, ["speeches", "move", "abc123", "--folder", "42"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_speakers_list_not_logged_in(runner, temp_config_dir):
    """Test speakers list when not logged in."""
    result = runner.invoke(main, ["speakers", "list"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_speakers_create_not_logged_in(runner, temp_config_dir):
    """Test speakers create when not logged in."""
    result = runner.invoke(main, ["speakers", "create", "Name"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_speakers_tag_not_logged_in(runner, temp_config_dir):
    """Test speakers tag when not logged in."""
    result = runner.invoke(main, ["speakers", "tag", "speech123", "s1"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_folders_list_not_logged_in(runner, temp_config_dir):
    """Test folders list when not logged in."""
    result = runner.invoke(main, ["folders", "list"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_folders_create_not_logged_in(runner, temp_config_dir):
    """Test folders create when not logged in."""
    result = runner.invoke(main, ["folders", "create", "Name"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_folders_rename_not_logged_in(runner, temp_config_dir):
    """Test folders rename when not logged in."""
    result = runner.invoke(main, ["folders", "rename", "f1", "New"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_groups_list_not_logged_in(runner, temp_config_dir):
    """Test groups list when not logged in."""
    result = runner.invoke(main, ["groups", "list"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


def test_user_not_logged_in_no_creds(runner, temp_config_dir):
    """Test user command when no credentials at all."""
    result = runner.invoke(main, ["user"])
    assert result.exit_code == 1
    assert "Not logged in" in result.output


# =============================================================================
# Speeches: list with untitled and missing fields
# =============================================================================


def test_speeches_list_untitled_and_missing_fields(runner, saved_credentials, mock_login):
    """Test speeches list with missing title and optional fields."""
    mock_login.get(
        API_BASE + "speeches",
        json={
            "speeches": [
                {
                    "otid": "abc123",
                    "title": None,
                    "created_at": 0,
                    "duration": 0,
                    "live_status": "",
                    "folder": None,
                    "speakers": [],
                },
            ]
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "list"])
    assert result.exit_code == 0
    assert "Untitled" in result.output
    assert "abc123" in result.output


# =============================================================================
# Speeches: get with transcripts at top level
# =============================================================================


def test_speeches_get_transcripts_at_top_level(runner, saved_credentials, mock_login):
    """Test speech get when transcripts are at top-level data, not nested in speech."""
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "title": "Top Level Transcripts",
                "otid": "abc123",
                "created_at": 0,
                "duration": 0,
            },
            "transcripts": [
                {"speaker_name": "Host", "transcript": "Welcome to the show"},
            ],
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "get", "abc123"])
    assert result.exit_code == 0
    assert "Transcript:" in result.output
    assert "[Host]: Welcome to the show" in result.output


# =============================================================================
# Speeches: search with --size option
# =============================================================================


def test_speeches_search_with_size(runner, saved_credentials, mock_login):
    """Test speech search with custom --size option."""
    mock_login.get(
        API_BASE + "advanced_search",
        json={"results": [{"transcript": "Found"}]},
        status=200,
    )
    result = runner.invoke(
        main, ["speeches", "search", "query", "abc123", "--size", "10"]
    )
    assert result.exit_code == 0
    assert "Found" in result.output


# =============================================================================
# Speeches: download with default format (txt)
# =============================================================================


def test_speeches_download_markdown(runner, saved_credentials, mock_login, tmp_path, monkeypatch):
    """Test downloading a speech as markdown."""
    monkeypatch.chdir(tmp_path)
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "title": "My Meeting",
                "otid": "abc123",
                "created_at": 1704067200,
                "start_time": 1704067200,
                "end_time": 1704074400,
                "summary": "Weekly sync",
                "duration": 7200,
                "speech_id": "SP123",
                "folder": {"folder_name": "Work", "id": "f1"},
                "speakers": [{"speaker_name": "Alice"}, {"speaker_name": "Bob"}],
                "transcripts": [
                    {"speaker_name": "Alice", "transcript": "Hello everyone"},
                    {"speaker_name": "Bob", "transcript": "Hi Alice"},
                ],
            }
        },
        status=200,
    )
    result = runner.invoke(main, ["speeches", "download", "abc123", "--format", "md"])
    assert result.exit_code == 0
    assert "Downloaded: abc123.md" in result.output
    md_file = tmp_path / "abc123.md"
    assert md_file.exists()
    content = md_file.read_text()
    assert content.startswith("---\n")
    assert 'title: "My Meeting"' in content
    assert 'summary: "Weekly sync"' in content
    assert 'start_time: "2024-01-01T00:00:00Z"' in content
    assert 'end_time: "2024-01-01T02:00:00Z"' in content
    assert "duration_seconds: 7200" in content
    assert 'source: "otter.ai"' in content
    assert 'speech_id: "SP123"' in content
    assert 'folder: "Work"' in content
    assert "speakers:" in content
    assert '  - "Alice"' in content
    assert '  - "Bob"' in content
    assert "# My Meeting" in content
    assert "## Transcript" in content
    assert "**Alice:** Hello everyone" in content
    assert "**Bob:** Hi Alice" in content


def test_speeches_download_markdown_with_name(runner, saved_credentials, mock_login, tmp_path, monkeypatch):
    """Test markdown download with custom output filename."""
    monkeypatch.chdir(tmp_path)
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "title": "Meeting",
                "otid": "abc123",
                "created_at": 0,
                "duration": 0,
            }
        },
        status=200,
    )
    result = runner.invoke(
        main, ["speeches", "download", "abc123", "--format", "md", "--output", "myfile"]
    )
    assert result.exit_code == 0
    assert "Downloaded: myfile.md" in result.output
    assert (tmp_path / "myfile.md").exists()


def test_speeches_download_markdown_alias(runner, saved_credentials, mock_login, tmp_path, monkeypatch):
    """Test that --format markdown works as alias for md."""
    monkeypatch.chdir(tmp_path)
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "title": "Test",
                "otid": "abc123",
                "created_at": 0,
                "duration": 0,
            }
        },
        status=200,
    )
    result = runner.invoke(
        main, ["speeches", "download", "abc123", "--format", "markdown"]
    )
    assert result.exit_code == 0
    assert "Downloaded: abc123.md" in result.output
    assert (tmp_path / "abc123.md").exists()


def test_speeches_download_markdown_custom_frontmatter_fields(
    runner, saved_credentials, mock_login, tmp_path, monkeypatch
):
    """Test markdown download with custom field selection."""
    monkeypatch.chdir(tmp_path)
    mock_login.get(
        API_BASE + "speech",
        json={
            "speech": {
                "title": "Custom Fields",
                "speech_id": "sp42",
                "summary": "S",
                "duration": 120,
                "transcripts": [{"transcript": "Hello"}],
            }
        },
        status=200,
    )
    result = runner.invoke(
        main,
        [
            "speeches",
            "download",
            "abc123",
            "--format",
            "md",
            "--frontmatter-fields",
            "speech_id,title",
        ],
    )
    assert result.exit_code == 0
    content = (tmp_path / "abc123.md").read_text()
    assert 'speech_id: "sp42"' in content
    assert 'title: "Custom Fields"' in content
    assert 'summary: "S"' not in content


def test_speeches_download_markdown_invalid_frontmatter_field(
    runner, saved_credentials, mock_login
):
    """Test invalid frontmatter field exits with error."""
    result = runner.invoke(
        main,
        [
            "speeches",
            "download",
            "abc123",
            "--format",
            "md",
            "--frontmatter-fields",
            "title,invalid",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown frontmatter field" in result.output


def test_speeches_download_frontmatter_options_non_md_rejected(
    runner, saved_credentials, mock_login
):
    """Test md-only frontmatter options are rejected for non-md format."""
    result = runner.invoke(
        main,
        [
            "speeches",
            "download",
            "abc123",
            "--format",
            "txt",
            "--frontmatter-fields",
            "title",
        ],
    )
    assert result.exit_code == 1
    assert "only valid with md format" in result.output


def test_speeches_download_frontmatter_default_non_md_allowed(
    runner, saved_credentials, mock_login, tmp_path, monkeypatch
):
    """Test default/blank-equivalent frontmatter fields are no-op on non-md."""
    monkeypatch.chdir(tmp_path)
    mock_login.post(
        API_BASE + "bulk_export",
        body=b"txt content",
        status=200,
        content_type="application/octet-stream",
    )
    result = runner.invoke(
        main,
        [
            "speeches",
            "download",
            "abc123",
            "--format",
            "txt",
            "--frontmatter-fields",
            " DEFAULT ",
        ],
    )
    assert result.exit_code == 0
    assert (tmp_path / "abc123.txt").exists()


def test_speeches_download_markdown_api_failure(runner, saved_credentials, mock_login, tmp_path, monkeypatch):
    """Test markdown download when API returns error."""
    monkeypatch.chdir(tmp_path)
    mock_login.get(
        API_BASE + "speech",
        json={"error": "not found"},
        status=404,
    )
    result = runner.invoke(main, ["speeches", "download", "abc123", "--format", "md"])
    assert result.exit_code == 1
    assert "Failed to get speech" in result.output


def test_speeches_download_markdown_mixed_format_rejected(runner, saved_credentials, mock_login):
    """Test that combining md with other formats is rejected."""
    result = runner.invoke(
        main, ["speeches", "download", "abc123", "--format", "txt,md"]
    )
    assert result.exit_code == 1
    assert "cannot be combined" in result.output


def test_speeches_download_default_format(runner, saved_credentials, mock_login, tmp_path, monkeypatch):
    """Test download with default format (txt)."""
    monkeypatch.chdir(tmp_path)
    mock_login.post(
        API_BASE + "bulk_export",
        body=b"default format content",
        status=200,
        content_type="application/octet-stream",
    )
    result = runner.invoke(main, ["speeches", "download", "abc123"])
    assert result.exit_code == 0
    assert "Downloaded: abc123.txt" in result.output
    assert (tmp_path / "abc123.txt").exists()
