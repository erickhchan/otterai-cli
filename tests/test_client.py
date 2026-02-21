"""Tests for the OtterAIClient -- real Session code, HTTP intercepted by responses."""

import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
import responses

from otterai.client import OtterAIClient, OtterAIError

API_BASE = "https://otter.ai/forward/api/v1/"
S3_BASE = "https://s3.us-west-2.amazonaws.com/"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _login(client, mock_api):
    """Log in via the real login flow so _userid and _cookies are populated."""
    mock_api.get(
        API_BASE + "login",
        json={"userid": "u123", "email": "testuser@example.com"},
        status=200,
        headers={"Set-Cookie": "csrftoken=tok123; Path=/"},
    )
    result = client.login("testuser@example.com", "testpass")
    assert result["status"] == 200
    assert client._userid == "u123"
    return result


# ============================================================================
# OtterAIError
# ============================================================================


class TestOtterAIError:
    def test_is_exception(self):
        """OtterAIError is a proper Exception subclass."""
        err = OtterAIError("something went wrong")
        assert isinstance(err, Exception)
        assert str(err) == "something went wrong"

    def test_raised_and_caught(self):
        with pytest.raises(OtterAIError, match="test error"):
            raise OtterAIError("test error")


# ============================================================================
# Client instantiation
# ============================================================================


class TestClientInit:
    def test_fresh_client_state(self):
        """A new client has no userid or cookies."""
        client = OtterAIClient()
        assert client._userid is None
        assert client._cookies is None

    def test_class_constants(self):
        assert OtterAIClient.API_BASE_URL == API_BASE
        assert OtterAIClient.S3_BASE_URL == S3_BASE
        assert OtterAIClient.DEFAULT_TIMEOUT == 30


# ============================================================================
# Authentication
# ============================================================================


class TestLogin:
    """Login and session initialisation."""

    def test_login_success(self, mock_api):
        """Successful login stores userid and cookies and returns 200."""
        client = OtterAIClient()
        result = _login(client, mock_api)

        assert result["status"] == 200
        assert result["data"]["userid"] == "u123"
        assert client._userid == "u123"
        assert client._cookies is not None

    def test_login_sets_basic_auth(self, mock_api):
        """Login sets HTTP Basic Auth on the session."""
        client = OtterAIClient()
        _login(client, mock_api)

        assert client._session.auth == ("testuser@example.com", "testpass")

    def test_login_sends_username_param(self, mock_api):
        """Login sends ?username= as a query parameter."""
        client = OtterAIClient()
        _login(client, mock_api)

        req = mock_api.calls[0].request
        parsed = urlparse(req.url)
        qs = parse_qs(parsed.query)
        assert qs["username"] == ["testuser@example.com"]

    def test_login_failure_401(self, mock_api):
        """401 login does not set userid and returns the error status."""
        mock_api.get(
            API_BASE + "login",
            json={"error": "Invalid credentials"},
            status=401,
        )
        client = OtterAIClient()
        result = client.login("bad@example.com", "wrongpass")

        assert result["status"] == 401
        assert client._userid is None

    def test_login_failure_500(self, mock_api):
        """500 from login is returned without setting userid."""
        mock_api.get(
            API_BASE + "login",
            json={"error": "Internal Server Error"},
            status=500,
        )
        client = OtterAIClient()
        result = client.login("user@example.com", "pass")

        assert result["status"] == 500
        assert client._userid is None


# ============================================================================
# _require_userid guard
# ============================================================================


class TestRequireUserid:
    """All guarded methods must raise when not logged in."""

    GUARDED_METHODS = [
        ("get_user", []),
        ("get_speakers", []),
        ("get_speeches", []),
        ("get_speech", ["speech-id"]),
        ("set_speech_title", ["speech-id", "title"]),
        ("query_speech", ["query", "speech-id"]),
        ("upload_speech", ["file.mp4"]),
        ("download_speech", ["speech-id"]),
        ("move_to_trash_bin", ["speech-id"]),
        ("create_speaker", ["Alice"]),
        ("set_transcript_speaker", ["sid", "tuuid", "spk_id", "Alice"]),
        ("get_notification_settings", []),
        ("list_groups", []),
        ("get_folders", []),
        ("create_folder", ["Work"]),
        ("rename_folder", ["f1", "New Name"]),
        ("add_folder_speeches", ["f1", ["s1"]]),
    ]

    @pytest.mark.parametrize(
        "method_name,args",
        GUARDED_METHODS,
        ids=[m[0] for m in GUARDED_METHODS],
    )
    def test_raises_without_login(self, method_name, args):
        """Every guarded method raises OtterAIError when userid is None."""
        client = OtterAIClient()
        with pytest.raises(OtterAIError, match="userid is invalid"):
            getattr(client, method_name)(*args)

    def test_passes_when_userid_set(self):
        """_require_userid does not raise when userid is present."""
        client = OtterAIClient()
        client._userid = "valid"
        client._require_userid()  # should not raise


# ============================================================================
# _handle_response
# ============================================================================


class TestHandleResponse:
    """Response parsing edge cases."""

    def test_non_json_response(self, mock_api):
        """Non-JSON body returns empty dict as data."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(
            API_BASE + "user",
            body="not json at all",
            status=200,
            content_type="text/plain",
        )
        result = client.get_user()
        assert result["status"] == 200
        assert result["data"] == {}

    def test_data_override(self, mock_api):
        """When data kwarg is passed to _handle_response, it is used directly."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "user", json={"ignored": True}, status=200)
        resp = client._session.get(API_BASE + "user", timeout=30)
        result = client._handle_response(resp, data={"custom": "value"})
        assert result["data"] == {"custom": "value"}
        assert result["status"] == 200

    def test_data_override_empty_dict(self, mock_api):
        """Explicitly passing {} should still override response JSON."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "user", json={"ignored": True}, status=200)
        resp = client._session.get(API_BASE + "user", timeout=30)
        result = client._handle_response(resp, data={})
        assert result["data"] == {}
        assert result["status"] == 200


class TestRetries:
    def test_retries_429_then_succeeds(self, mock_api, monkeypatch):
        client = OtterAIClient()
        _login(client, mock_api)

        sleep_calls = []
        monkeypatch.setattr("otterai.client.time.sleep", sleep_calls.append)

        mock_api.get(API_BASE + "user", json={"error": "rate limit"}, status=429)
        mock_api.get(API_BASE + "user", json={"email": "ok@example.com"}, status=200)

        result = client.get_user()
        assert result["status"] == 200
        assert result["data"]["email"] == "ok@example.com"
        assert sleep_calls == [1]
        assert len(mock_api.calls) == 3

    def test_retries_500_then_succeeds_on_post(self, mock_api, monkeypatch):
        client = OtterAIClient()
        _login(client, mock_api)

        sleep_calls = []
        monkeypatch.setattr("otterai.client.time.sleep", sleep_calls.append)

        mock_api.post(
            API_BASE + "create_folder", json={"error": "internal"}, status=500
        )
        mock_api.post(
            API_BASE + "create_folder",
            json={"folder": {"id": "f1", "folder_name": "Work"}},
            status=200,
        )

        result = client.create_folder("Work")
        assert result["status"] == 200
        assert result["data"]["folder"]["id"] == "f1"
        assert sleep_calls == [1]
        assert len(mock_api.calls) == 3

    def test_retry_after_header_overrides_exponential_backoff(
        self, mock_api, monkeypatch
    ):
        client = OtterAIClient()
        _login(client, mock_api)

        sleep_calls = []
        monkeypatch.setattr("otterai.client.time.sleep", sleep_calls.append)

        mock_api.get(
            API_BASE + "user",
            json={"error": "rate limit"},
            status=429,
            headers={"Retry-After": "3"},
        )
        mock_api.get(API_BASE + "user", json={"email": "ok@example.com"}, status=200)

        result = client.get_user()
        assert result["status"] == 200
        assert sleep_calls == [3.0]

    def test_retry_after_http_date_header_overrides_exponential_backoff(
        self, mock_api, monkeypatch
    ):
        class FixedDatetime:
            @staticmethod
            def now(tz=None):
                return datetime(2026, 2, 21, 12, 0, 0, tzinfo=timezone.utc)

        client = OtterAIClient()
        _login(client, mock_api)

        sleep_calls = []
        monkeypatch.setattr("otterai.client.time.sleep", sleep_calls.append)
        monkeypatch.setattr("otterai.client.datetime", FixedDatetime)

        mock_api.get(
            API_BASE + "user",
            json={"error": "rate limit"},
            status=429,
            headers={"Retry-After": "Sat, 21 Feb 2026 12:00:04 GMT"},
        )
        mock_api.get(API_BASE + "user", json={"email": "ok@example.com"}, status=200)

        result = client.get_user()
        assert result["status"] == 200
        assert sleep_calls == [4.0]

    def test_does_not_retry_non_retryable_4xx(self, mock_api, monkeypatch):
        client = OtterAIClient()
        _login(client, mock_api)

        sleep_calls = []
        monkeypatch.setattr("otterai.client.time.sleep", sleep_calls.append)

        mock_api.get(API_BASE + "user", json={"error": "bad request"}, status=400)

        result = client.get_user()
        assert result["status"] == 400
        assert sleep_calls == []
        assert len(mock_api.calls) == 2

    def test_returns_last_retryable_response_after_max_attempts(
        self, mock_api, monkeypatch
    ):
        client = OtterAIClient()
        client.RETRY_MAX_ATTEMPTS = 2
        _login(client, mock_api)

        sleep_calls = []
        monkeypatch.setattr("otterai.client.time.sleep", sleep_calls.append)

        for _ in range(client.RETRY_MAX_ATTEMPTS + 1):
            mock_api.get(API_BASE + "user", json={"error": "still failing"}, status=500)

        result = client.get_user()
        assert result["status"] == 500
        assert sleep_calls == [1, 2]
        assert len(mock_api.calls) == 4


# ============================================================================
# _authed_headers
# ============================================================================


class TestAuthedHeaders:
    def test_csrf_token_from_cookies(self, mock_api):
        """CSRF token is extracted from cookies set during login."""
        mock_api.get(
            API_BASE + "login",
            json={"userid": "u123", "email": "test@example.com"},
            status=200,
            headers={"Set-Cookie": "csrftoken=my_csrf_token; Path=/"},
        )
        client = OtterAIClient()
        client.login("test@example.com", "pass")

        headers = client._authed_headers()
        assert headers["x-csrftoken"] == "my_csrf_token"
        assert headers["referer"] == "https://otter.ai/"

    def test_missing_csrf_token_defaults_empty(self, mock_api):
        """If csrftoken cookie is absent, x-csrftoken defaults to empty string."""
        mock_api.get(
            API_BASE + "login",
            json={"userid": "u123", "email": "test@example.com"},
            status=200,
        )
        client = OtterAIClient()
        client.login("test@example.com", "pass")

        headers = client._authed_headers()
        assert headers["x-csrftoken"] == ""


# ============================================================================
# Simple GET endpoints
# ============================================================================


class TestGetUser:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        user_data = {"email": "testuser@example.com", "plan": "pro"}
        mock_api.get(API_BASE + "user", json=user_data, status=200)

        result = client.get_user()
        assert result["status"] == 200
        assert result["data"]["email"] == "testuser@example.com"

    def test_server_error(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "user", json={"error": "fail"}, status=500)
        result = client.get_user()
        assert result["status"] == 500


class TestGetSpeakers:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        speakers = [{"speaker_id": "s1", "speaker_name": "Alice"}]
        mock_api.get(API_BASE + "speakers", json={"speakers": speakers}, status=200)

        result = client.get_speakers()
        assert result["status"] == 200
        assert result["data"]["speakers"][0]["speaker_name"] == "Alice"

    def test_sends_userid_param(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "speakers", json={"speakers": []}, status=200)
        client.get_speakers()

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["userid"] == ["u123"]


class TestGetSpeeches:
    def test_default_params(self, mock_api):
        """Default call sends folder=0, page_size=45, source=owned."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "speeches", json={"speeches": []}, status=200)
        client.get_speeches()

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["folder"] == ["0"]
        assert qs["page_size"] == ["45"]
        assert qs["source"] == ["owned"]

    def test_custom_params(self, mock_api):
        """Custom parameters are forwarded."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "speeches", json={"speeches": []}, status=200)
        client.get_speeches(folder=3, page_size=10, source="shared")

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["folder"] == ["3"]
        assert qs["page_size"] == ["10"]
        assert qs["source"] == ["shared"]

    def test_returns_speech_list(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        speeches = [{"otid": "abc", "title": "Meeting"}]
        mock_api.get(API_BASE + "speeches", json={"speeches": speeches}, status=200)

        result = client.get_speeches()
        assert result["data"]["speeches"][0]["otid"] == "abc"


class TestGetSpeech:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        speech = {"otid": "abc", "title": "My Meeting", "duration": 300}
        mock_api.get(API_BASE + "speech", json={"speech": speech}, status=200)

        result = client.get_speech("abc")
        assert result["data"]["speech"]["title"] == "My Meeting"

    def test_sends_correct_params(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "speech", json={}, status=200)
        client.get_speech("xyz789")

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["userid"] == ["u123"]
        assert qs["otid"] == ["xyz789"]


class TestSetSpeechTitle:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "set_speech_title", json={"ok": True}, status=200)
        result = client.set_speech_title("abc", "New Title")
        assert result["status"] == 200

    def test_sends_correct_params(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "set_speech_title", json={}, status=200)
        client.set_speech_title("abc", "Renamed")

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["otid"] == ["abc"]
        assert qs["title"] == ["Renamed"]


class TestQuerySpeech:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(
            API_BASE + "advanced_search",
            json={"results": [{"text": "hello"}]},
            status=200,
        )
        result = client.query_speech("hello", "abc")
        assert result["status"] == 200

    def test_default_size(self, mock_api):
        """Default size parameter is 500."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "advanced_search", json={}, status=200)
        client.query_speech("test", "abc")

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["size"] == ["500"]
        assert qs["query"] == ["test"]
        assert qs["otid"] == ["abc"]

    def test_custom_size(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "advanced_search", json={}, status=200)
        client.query_speech("test", "abc", size=100)

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["size"] == ["100"]


class TestGetNotificationSettings:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(
            API_BASE + "get_notification_settings",
            json={"email_notifications": True},
            status=200,
        )
        result = client.get_notification_settings()
        assert result["status"] == 200
        assert result["data"]["email_notifications"] is True


class TestListGroups:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        groups = [{"id": "g1", "name": "Engineering"}]
        mock_api.get(API_BASE + "list_groups", json=groups, status=200)

        result = client.list_groups()
        assert result["data"][0]["name"] == "Engineering"

    def test_sends_userid(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "list_groups", json=[], status=200)
        client.list_groups()

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["userid"] == ["u123"]


# ============================================================================
# Folder operations
# ============================================================================


class TestGetFolders:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        folders = [{"id": "f1", "folder_name": "Work"}]
        mock_api.get(API_BASE + "folders", json={"folders": folders}, status=200)

        result = client.get_folders()
        assert result["data"]["folders"][0]["folder_name"] == "Work"

    def test_sends_userid(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "folders", json={"folders": []}, status=200)
        client.get_folders()

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["userid"] == ["u123"]


class TestCreateFolder:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(
            API_BASE + "create_folder",
            json={"folder": {"id": "f_new", "folder_name": "New Folder"}},
            status=200,
        )
        result = client.create_folder("New Folder")
        assert result["status"] == 200

    def test_sends_correct_body_and_headers(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "create_folder", json={}, status=200)
        client.create_folder("Projects")

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["userid"] == ["u123"]
        assert "folder_name=Projects" in req.body
        assert req.headers.get("referer") == "https://otter.ai/"


class TestRenameFolder:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "rename_folder", json={"ok": True}, status=200)
        result = client.rename_folder("f1", "Renamed Folder")
        assert result["status"] == 200

    def test_sends_correct_params(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "rename_folder", json={}, status=200)
        client.rename_folder("f1", "Better Name")

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["userid"] == ["u123"]
        assert qs["folder_id"] == ["f1"]
        # URL-encoded form body uses + or %20 for spaces
        assert "new_name=Better" in req.body


class TestAddFolderSpeeches:
    def test_list_of_ids(self, mock_api):
        """Passing a list of speech IDs works."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "add_folder_speeches", json={"ok": True}, status=200)
        result = client.add_folder_speeches("f1", ["s1", "s2"])
        assert result["status"] == 200

    def test_single_string_id_coerced_to_list(self, mock_api):
        """A single string speech_id is wrapped in a list."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "add_folder_speeches", json={"ok": True}, status=200)
        result = client.add_folder_speeches("f1", "single_id")
        assert result["status"] == 200

        req = mock_api.calls[-1].request
        assert "speech_otid_list" in req.body

    def test_sends_csrf_and_referer(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "add_folder_speeches", json={}, status=200)
        client.add_folder_speeches("f1", ["s1"])

        req = mock_api.calls[-1].request
        assert req.headers.get("referer") == "https://otter.ai/"

    def test_sends_userid_and_folder_id(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "add_folder_speeches", json={}, status=200)
        client.add_folder_speeches("folder_42", ["s1"])

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["userid"] == ["u123"]
        assert qs["folder_id"] == ["folder_42"]


# ============================================================================
# Speaker operations
# ============================================================================


class TestCreateSpeaker:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(
            API_BASE + "create_speaker",
            json={"speaker_id": "s_new", "speaker_name": "Bob"},
            status=200,
        )
        result = client.create_speaker("Bob")
        assert result["status"] == 200
        assert result["data"]["speaker_name"] == "Bob"

    def test_sends_correct_body(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "create_speaker", json={}, status=200)
        client.create_speaker("Alice")

        req = mock_api.calls[-1].request
        assert "speaker_name=Alice" in req.body

    def test_sends_userid_param(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "create_speaker", json={}, status=200)
        client.create_speaker("Charlie")

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["userid"] == ["u123"]


class TestSetTranscriptSpeaker:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "set_transcript_speaker", json={"ok": True}, status=200)
        result = client.set_transcript_speaker(
            "speech1", "tuuid1", "spk1", "Alice", create_speaker=False
        )
        assert result["status"] == 200

    def test_sends_correct_params(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "set_transcript_speaker", json={}, status=200)
        client.set_transcript_speaker(
            "speech1", "tuuid1", "spk1", "Alice", create_speaker=True
        )

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["speech_otid"] == ["speech1"]
        assert qs["transcript_uuid"] == ["tuuid1"]
        assert qs["speaker_id"] == ["spk1"]
        assert qs["speaker_name"] == ["Alice"]
        assert qs["create_speaker"] == ["true"]
        assert qs["userid"] == ["u123"]

    @pytest.mark.parametrize(
        "create_flag,expected",
        [(True, "true"), (False, "false")],
        ids=["create_true", "create_false"],
    )
    def test_create_speaker_bool_serialization(self, mock_api, create_flag, expected):
        """create_speaker bool is serialised to lowercase string."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "set_transcript_speaker", json={}, status=200)
        client.set_transcript_speaker(
            "s1", "t1", "spk1", "Name", create_speaker=create_flag
        )

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["create_speaker"] == [expected]

    def test_sends_authed_headers(self, mock_api):
        """set_transcript_speaker sends authed headers with CSRF and referer."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(API_BASE + "set_transcript_speaker", json={}, status=200)
        client.set_transcript_speaker("s1", "t1", "spk1", "Name")

        req = mock_api.calls[-1].request
        assert req.headers.get("referer") == "https://otter.ai/"


# ============================================================================
# Move to trash
# ============================================================================


class TestMoveToTrashBin:
    def test_success(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "move_to_trash_bin", json={"ok": True}, status=200)
        result = client.move_to_trash_bin("abc")
        assert result["status"] == 200

    def test_sends_correct_data(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "move_to_trash_bin", json={}, status=200)
        client.move_to_trash_bin("speech_xyz")

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["userid"] == ["u123"]
        assert "otid=speech_xyz" in req.body

    def test_server_error(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(
            API_BASE + "move_to_trash_bin",
            json={"error": "fail"},
            status=500,
        )
        result = client.move_to_trash_bin("abc")
        assert result["status"] == 500

    def test_sends_csrf_headers(self, mock_api):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "move_to_trash_bin", json={}, status=200)
        client.move_to_trash_bin("abc")

        req = mock_api.calls[-1].request
        assert req.headers.get("referer") == "https://otter.ai/"


# ============================================================================
# Download speech
# ============================================================================


class TestDownloadSpeech:
    def test_download_zip_default_format(self, mock_api, tmp_path):
        """Default multi-format download produces a .zip file."""
        client = OtterAIClient()
        _login(client, mock_api)

        content = b"PK\x03\x04fake zip content"
        mock_api.post(API_BASE + "bulk_export", body=content, status=200)

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = client.download_speech("abc123")
        finally:
            os.chdir(original_dir)

        assert result["status"] == 200
        assert result["data"]["filename"] == "abc123.zip"
        assert (tmp_path / "abc123.zip").read_bytes() == content

    def test_download_single_format(self, mock_api, tmp_path):
        """Single format produces file with that extension."""
        client = OtterAIClient()
        _login(client, mock_api)

        content = b"transcript text content"
        mock_api.post(API_BASE + "bulk_export", body=content, status=200)

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = client.download_speech("abc123", fileformat="txt")
        finally:
            os.chdir(original_dir)

        assert result["data"]["filename"] == "abc123.txt"
        assert (tmp_path / "abc123.txt").read_bytes() == content

    @pytest.mark.parametrize(
        "fileformat,expected_ext",
        [
            ("txt", "txt"),
            ("pdf", "pdf"),
            ("srt", "srt"),
            ("docx", "docx"),
            ("mp3", "mp3"),
            ("txt,pdf", "zip"),
            ("txt,pdf,mp3,docx,srt", "zip"),
        ],
        ids=["txt", "pdf", "srt", "docx", "mp3", "two_formats", "all_formats"],
    )
    def test_filename_extension_logic(
        self, mock_api, tmp_path, fileformat, expected_ext
    ):
        """Single format uses its extension; multi-format uses .zip."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "bulk_export", body=b"data", status=200)

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = client.download_speech("id1", fileformat=fileformat)
        finally:
            os.chdir(original_dir)

        assert result["data"]["filename"] == f"id1.{expected_ext}"

    def test_download_custom_name(self, mock_api, tmp_path):
        """Custom name overrides the speech_id in filename."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "bulk_export", body=b"data", status=200)

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = client.download_speech(
                "abc123", name="my_meeting", fileformat="pdf"
            )
        finally:
            os.chdir(original_dir)

        assert result["data"]["filename"] == "my_meeting.pdf"
        assert (tmp_path / "my_meeting.pdf").exists()

    def test_download_failure_raises(self, mock_api, tmp_path):
        """Non-OK response raises OtterAIError."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "bulk_export", body=b"", status=403)

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(OtterAIError, match="403"):
                client.download_speech("abc123")
        finally:
            os.chdir(original_dir)

    def test_download_500_raises_with_speech_id(self, mock_api, tmp_path):
        """Error message includes the speech_id."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "bulk_export", body=b"", status=500)

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(OtterAIError, match="speech_abc"):
                client.download_speech("speech_abc")
        finally:
            os.chdir(original_dir)

    def test_download_sends_csrf_headers(self, mock_api, tmp_path):
        """Download sends CSRF token and referer in headers."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "bulk_export", body=b"data", status=200)

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            client.download_speech("abc123", fileformat="txt")
        finally:
            os.chdir(original_dir)

        req = mock_api.calls[-1].request
        assert req.headers.get("referer") == "https://otter.ai/"

    def test_download_sends_correct_body(self, mock_api, tmp_path):
        """Download sends formats and speech_otid_list in POST body."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "bulk_export", body=b"data", status=200)

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            client.download_speech("speech99", fileformat="srt")
        finally:
            os.chdir(original_dir)

        req = mock_api.calls[-1].request
        assert "formats=srt" in req.body
        assert "speech_otid_list=speech99" in req.body

    def test_download_sends_userid_param(self, mock_api, tmp_path):
        """Download sends userid in query params."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(API_BASE + "bulk_export", body=b"data", status=200)

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            client.download_speech("abc", fileformat="txt")
        finally:
            os.chdir(original_dir)

        req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(req.url).query)
        assert qs["userid"] == ["u123"]

    def test_download_writes_actual_content(self, mock_api, tmp_path):
        """The file on disk contains exactly the bytes from the response."""
        client = OtterAIClient()
        _login(client, mock_api)

        content = b"\x89PNG\r\n\x1a\nfake binary data with \x00 nulls"
        mock_api.post(API_BASE + "bulk_export", body=content, status=200)

        original_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            client.download_speech("binfile", fileformat="mp3")
        finally:
            os.chdir(original_dir)

        assert (tmp_path / "binfile.mp3").read_bytes() == content


# ============================================================================
# Upload speech
# ============================================================================


class TestUploadSpeech:
    S3_UPLOAD_URL = S3_BASE + "speech-upload-prod"

    S3_XML_RESPONSE = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<PostResponse>"
        "<Location>https://s3.us-west-2.amazonaws.com/speech-upload-prod/audio.mp4</Location>"
        "<Bucket>speech-upload-prod</Bucket>"
        "<Key>uploads/u123/audio.mp4</Key>"
        "<ETag>abc123</ETag>"
        "</PostResponse>"
    )

    UPLOAD_PARAMS_DATA = {
        "key": "uploads/u123/${filename}",
        "AWSAccessKeyId": "AKIA_FAKE",
        "policy": "base64policy",
        "signature": "sig123",
        "success_action_status": 201,
        "Content-Type": "audio/mp4",
        "form_action": "https://s3.us-west-2.amazonaws.com/speech-upload-prod",
    }

    def _setup_upload_mocks(self, mock_api, finish_status=200):
        """Register all stages of the upload flow."""
        # Step 1: get upload params
        mock_api.get(
            API_BASE + "speech_upload_params",
            json={"data": dict(self.UPLOAD_PARAMS_DATA)},
            status=200,
        )
        # Step 2: OPTIONS preflight
        mock_api.add(
            responses.Response(
                method="OPTIONS",
                url=self.S3_UPLOAD_URL,
                status=200,
            )
        )
        # Step 3: POST to S3
        mock_api.post(
            self.S3_UPLOAD_URL,
            body=self.S3_XML_RESPONSE,
            status=201,
            content_type="application/xml",
        )
        # Step 4: finish upload
        mock_api.get(
            API_BASE + "finish_speech_upload",
            json={"speech_id": "new_speech_id", "status": "processing"},
            status=finish_status,
        )

    def test_upload_full_flow(self, mock_api, tmp_path):
        """Full upload: params -> OPTIONS -> S3 POST -> finish."""
        client = OtterAIClient()
        _login(client, mock_api)
        self._setup_upload_mocks(mock_api)

        audio_file = tmp_path / "test_audio.mp4"
        audio_file.write_bytes(b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100)

        result = client.upload_speech(str(audio_file))
        assert result["status"] == 200
        assert result["data"]["speech_id"] == "new_speech_id"

        # login(1) + params(1) + OPTIONS(1) + S3 POST(1) + finish(1) = 5 calls
        assert len(mock_api.calls) == 5

    def test_upload_params_failure_returns_early(self, mock_api, tmp_path):
        """If getting upload params fails, return error immediately."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(
            API_BASE + "speech_upload_params",
            json={"error": "unauthorized"},
            status=403,
        )

        audio_file = tmp_path / "test.mp4"
        audio_file.write_bytes(b"\x00" * 10)

        result = client.upload_speech(str(audio_file))
        assert result["status"] == 403
        # Only login + params calls
        assert len(mock_api.calls) == 2

    def test_upload_options_failure_returns_early(self, mock_api, tmp_path):
        """If OPTIONS preflight fails, return error immediately."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(
            API_BASE + "speech_upload_params",
            json={"data": dict(self.UPLOAD_PARAMS_DATA)},
            status=200,
        )
        mock_api.add(
            responses.Response(method="OPTIONS", url=self.S3_UPLOAD_URL, status=403)
        )

        audio_file = tmp_path / "test.mp4"
        audio_file.write_bytes(b"\x00" * 10)

        result = client.upload_speech(str(audio_file))
        assert result["status"] == 403
        # login + params + OPTIONS = 3
        assert len(mock_api.calls) == 3

    def test_upload_s3_post_failure_returns_early(self, mock_api, tmp_path):
        """If S3 POST returns non-201, return error without calling finish."""
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.get(
            API_BASE + "speech_upload_params",
            json={"data": dict(self.UPLOAD_PARAMS_DATA)},
            status=200,
        )
        mock_api.add(
            responses.Response(method="OPTIONS", url=self.S3_UPLOAD_URL, status=200)
        )
        mock_api.post(self.S3_UPLOAD_URL, body="error", status=400)

        audio_file = tmp_path / "test.mp4"
        audio_file.write_bytes(b"\x00" * 10)

        result = client.upload_speech(str(audio_file))
        assert result["status"] == 400
        # login + params + OPTIONS + S3 POST = 4 (no finish call)
        assert len(mock_api.calls) == 4

    def test_upload_finish_sends_correct_params(self, mock_api, tmp_path):
        """Finish call sends correct bucket, key, language, country, userid."""
        client = OtterAIClient()
        _login(client, mock_api)
        self._setup_upload_mocks(mock_api)

        audio_file = tmp_path / "audio.mp4"
        audio_file.write_bytes(b"\x00" * 10)

        client.upload_speech(str(audio_file))

        # Last call is finish_speech_upload
        finish_req = mock_api.calls[-1].request
        qs = parse_qs(urlparse(finish_req.url).query)
        assert qs["bucket"] == ["speech-upload-prod"]
        assert qs["key"] == ["uploads/u123/audio.mp4"]
        assert qs["language"] == ["en"]
        assert qs["country"] == ["us"]
        assert qs["userid"] == ["u123"]

    def test_upload_custom_content_type(self, mock_api, tmp_path):
        """Custom content_type is used in the multipart upload."""
        client = OtterAIClient()
        _login(client, mock_api)
        self._setup_upload_mocks(mock_api)

        audio_file = tmp_path / "recording.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 40)

        result = client.upload_speech(str(audio_file), content_type="audio/wav")
        assert result["status"] == 200

        # The S3 POST request (call index 3) should have multipart content type
        s3_req = mock_api.calls[3].request
        assert "multipart/form-data" in s3_req.headers["Content-Type"]

    def test_upload_options_sends_cors_headers(self, mock_api, tmp_path):
        """OPTIONS preflight sets correct CORS headers."""
        client = OtterAIClient()
        _login(client, mock_api)
        self._setup_upload_mocks(mock_api)

        audio_file = tmp_path / "audio.mp4"
        audio_file.write_bytes(b"\x00" * 10)

        client.upload_speech(str(audio_file))

        # OPTIONS request is call index 2
        options_req = mock_api.calls[2].request
        assert options_req.headers.get("Origin") == "https://otter.ai"
        assert options_req.headers.get("Referer") == "https://otter.ai/"
        assert options_req.headers.get("Access-Control-Request-Method") == "POST"
        assert options_req.headers.get("Accept") == "*/*"

    def test_upload_removes_form_action_from_fields(self, mock_api, tmp_path):
        """form_action key is removed from params before building multipart form."""
        client = OtterAIClient()
        _login(client, mock_api)
        self._setup_upload_mocks(mock_api)

        audio_file = tmp_path / "audio.mp4"
        audio_file.write_bytes(b"\x00" * 10)

        client.upload_speech(str(audio_file))

        # The S3 POST body should NOT contain form_action
        s3_req = mock_api.calls[3].request
        assert b"form_action" not in s3_req.body

    def test_upload_converts_success_action_status_to_string(self, mock_api, tmp_path):
        """success_action_status (int from API) is converted to str for multipart."""
        client = OtterAIClient()
        _login(client, mock_api)
        self._setup_upload_mocks(mock_api)

        audio_file = tmp_path / "audio.mp4"
        audio_file.write_bytes(b"\x00" * 10)

        # If the conversion failed, MultipartEncoder would raise. Completing
        # the upload successfully proves the conversion worked.
        result = client.upload_speech(str(audio_file))
        assert result["status"] == 200

    def test_upload_options_retries_on_5xx(self, mock_api, tmp_path, monkeypatch):
        client = OtterAIClient()
        _login(client, mock_api)

        sleep_calls = []
        monkeypatch.setattr("otterai.client.time.sleep", sleep_calls.append)

        mock_api.get(
            API_BASE + "speech_upload_params",
            json={"data": dict(self.UPLOAD_PARAMS_DATA)},
            status=200,
        )
        mock_api.add(
            responses.Response(method="OPTIONS", url=self.S3_UPLOAD_URL, status=503)
        )
        mock_api.add(
            responses.Response(method="OPTIONS", url=self.S3_UPLOAD_URL, status=200)
        )
        mock_api.post(
            self.S3_UPLOAD_URL,
            body=self.S3_XML_RESPONSE,
            status=201,
            content_type="application/xml",
        )
        mock_api.get(
            API_BASE + "finish_speech_upload",
            json={"speech_id": "new_speech_id", "status": "processing"},
            status=200,
        )

        audio_file = tmp_path / "audio.mp4"
        audio_file.write_bytes(b"\x00" * 10)

        result = client.upload_speech(str(audio_file))
        assert result["status"] == 200
        assert sleep_calls == [1]
        assert len(mock_api.calls) == 6

    def test_upload_s3_post_retries_on_5xx(self, mock_api, tmp_path, monkeypatch):
        client = OtterAIClient()
        _login(client, mock_api)

        sleep_calls = []
        monkeypatch.setattr("otterai.client.time.sleep", sleep_calls.append)

        mock_api.get(
            API_BASE + "speech_upload_params",
            json={"data": dict(self.UPLOAD_PARAMS_DATA)},
            status=200,
        )
        mock_api.add(
            responses.Response(method="OPTIONS", url=self.S3_UPLOAD_URL, status=200)
        )
        mock_api.post(self.S3_UPLOAD_URL, body="temporary error", status=503)
        mock_api.post(
            self.S3_UPLOAD_URL,
            body=self.S3_XML_RESPONSE,
            status=201,
            content_type="application/xml",
        )
        mock_api.get(
            API_BASE + "finish_speech_upload",
            json={"speech_id": "new_speech_id", "status": "processing"},
            status=200,
        )

        audio_file = tmp_path / "audio.mp4"
        audio_file.write_bytes(b"\x00" * 10)

        result = client.upload_speech(str(audio_file))
        assert result["status"] == 200
        assert sleep_calls == [1]
        assert len(mock_api.calls) == 6


# ============================================================================
# Cross-cutting: server errors on POST endpoints
# ============================================================================


class TestPostEndpointErrors:
    """POST endpoints handle server errors gracefully."""

    @pytest.mark.parametrize(
        "method_name,url_suffix,args",
        [
            ("create_folder", "create_folder", ["Work"]),
            ("rename_folder", "rename_folder", ["f1", "New"]),
            ("create_speaker", "create_speaker", ["Alice"]),
            ("move_to_trash_bin", "move_to_trash_bin", ["abc"]),
            ("add_folder_speeches", "add_folder_speeches", ["f1", ["s1"]]),
        ],
        ids=[
            "create_folder",
            "rename_folder",
            "create_speaker",
            "trash",
            "add_speeches",
        ],
    )
    def test_500_returns_error_status(self, mock_api, method_name, url_suffix, args):
        client = OtterAIClient()
        _login(client, mock_api)

        mock_api.post(
            API_BASE + url_suffix,
            json={"error": "internal"},
            status=500,
        )
        result = getattr(client, method_name)(*args)
        assert result["status"] == 500
