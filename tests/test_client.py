"""Tests for the API client module."""

from unittest.mock import MagicMock, patch, mock_open

import pytest

from otterai.client import OtterAIClient, OtterAIError


def test_otterai_error():
    """Test OtterAIError is a proper exception."""
    with pytest.raises(OtterAIError, match="Test error"):
        raise OtterAIError("Test error")


def test_client_instantiation():
    """Test client creates with empty state."""
    client = OtterAIClient()
    assert client._userid is None
    assert client._cookies is None


def test_require_userid_raises():
    """Test _require_userid raises when no userid."""
    client = OtterAIClient()
    with pytest.raises(OtterAIError, match="userid is invalid"):
        client._require_userid()


def test_require_userid_passes():
    """Test _require_userid passes when userid is set."""
    client = OtterAIClient()
    client._userid = "validid"
    client._require_userid()  # Should not raise


def test_handle_response_with_json():
    """Test _handle_response parses JSON."""
    client = OtterAIClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"key": "value"}

    result = client._handle_response(mock_resp)
    assert result == {"status": 200, "data": {"key": "value"}}


def test_handle_response_with_data_override():
    """Test _handle_response uses data param when provided."""
    client = OtterAIClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    result = client._handle_response(mock_resp, data={"custom": True})
    assert result == {"status": 200, "data": {"custom": True}}


def test_handle_response_invalid_json():
    """Test _handle_response handles non-JSON response."""
    client = OtterAIClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.json.side_effect = ValueError("No JSON")

    result = client._handle_response(mock_resp)
    assert result == {"status": 500, "data": {}}


def test_authed_headers():
    """Test _authed_headers returns correct headers."""
    client = OtterAIClient()
    client._cookies = {"csrftoken": "abc123"}

    headers = client._authed_headers()
    assert headers == {
        "x-csrftoken": "abc123",
        "referer": "https://otter.ai/",
    }


def test_authed_headers_missing_csrf():
    """Test _authed_headers with missing csrftoken."""
    client = OtterAIClient()
    client._cookies = {}

    headers = client._authed_headers()
    assert headers["x-csrftoken"] == ""


class TestLogin:
    def test_login_success(self):
        """Test successful login sets userid and cookies."""
        client = OtterAIClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"userid": "u123", "email": "a@b.com"}
        mock_resp.cookies.get_dict.return_value = {"csrftoken": "tok"}

        with patch.object(client._session, "get", return_value=mock_resp):
            result = client.login("user", "pass")

        assert result["status"] == 200
        assert client._userid == "u123"
        assert client._cookies == {"csrftoken": "tok"}

    def test_login_failure(self):
        """Test failed login does not set userid."""
        client = OtterAIClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": "bad creds"}

        with patch.object(client._session, "get", return_value=mock_resp):
            result = client.login("user", "badpass")

        assert result["status"] == 401
        assert client._userid is None

    def test_login_passes_timeout(self):
        """Test login passes timeout to session.get."""
        client = OtterAIClient()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {}

        with patch.object(client._session, "get", return_value=mock_resp) as mock_get:
            client.login("user", "pass")
            _, kwargs = mock_get.call_args
            assert kwargs["timeout"] == OtterAIClient.DEFAULT_TIMEOUT


class TestRequiresUserid:
    """Test that methods requiring userid raise OtterAIError when not logged in."""

    @pytest.mark.parametrize(
        "method,args",
        [
            ("get_user", []),
            ("get_speakers", []),
            ("get_speeches", []),
            ("get_speech", ["id"]),
            ("set_speech_title", ["id", "title"]),
            ("query_speech", ["q", "id"]),
            ("upload_speech", ["file.mp4"]),
            ("download_speech", ["id"]),
            ("move_to_trash_bin", ["id"]),
            ("create_speaker", ["name"]),
            ("set_transcript_speaker", ["sid", "uuid", "spkid", "name"]),
            ("get_notification_settings", []),
            ("list_groups", []),
            ("get_folders", []),
            ("create_folder", ["name"]),
            ("rename_folder", ["fid", "name"]),
            ("add_folder_speeches", ["fid", ["s1"]]),
        ],
    )
    def test_requires_userid(self, method, args):
        client = OtterAIClient()
        with pytest.raises(OtterAIError, match="userid is invalid"):
            getattr(client, method)(*args)


class TestApiMethods:
    """Test API methods with mocked HTTP responses."""

    @pytest.fixture
    def authed_client(self):
        client = OtterAIClient()
        client._userid = "u123"
        client._cookies = {"csrftoken": "tok"}
        return client

    def _mock_response(self, status=200, json_data=None):
        resp = MagicMock()
        resp.status_code = status
        resp.ok = status < 400
        resp.json.return_value = json_data or {}
        return resp

    def test_get_user(self, authed_client):
        resp = self._mock_response(json_data={"user": {"email": "a@b.com"}})
        with patch.object(authed_client._session, "get", return_value=resp):
            result = authed_client.get_user()
        assert result["status"] == 200
        assert result["data"]["user"]["email"] == "a@b.com"

    def test_get_speakers(self, authed_client):
        resp = self._mock_response(json_data={"speakers": []})
        with patch.object(authed_client._session, "get", return_value=resp):
            result = authed_client.get_speakers()
        assert result["status"] == 200

    def test_get_speeches(self, authed_client):
        resp = self._mock_response(json_data={"speeches": [{"otid": "x"}]})
        with patch.object(authed_client._session, "get", return_value=resp):
            result = authed_client.get_speeches()
        assert result["data"]["speeches"][0]["otid"] == "x"

    def test_get_speech(self, authed_client):
        resp = self._mock_response(json_data={"speech": {"otid": "abc"}})
        with patch.object(authed_client._session, "get", return_value=resp):
            result = authed_client.get_speech("abc")
        assert result["data"]["speech"]["otid"] == "abc"

    def test_set_speech_title(self, authed_client):
        resp = self._mock_response(json_data={"status": "ok"})
        with patch.object(authed_client._session, "get", return_value=resp):
            result = authed_client.set_speech_title("abc", "New Title")
        assert result["status"] == 200

    def test_query_speech(self, authed_client):
        resp = self._mock_response(json_data={"results": []})
        with patch.object(authed_client._session, "get", return_value=resp):
            result = authed_client.query_speech("test", "abc")
        assert result["status"] == 200

    def test_move_to_trash_bin(self, authed_client):
        resp = self._mock_response(json_data={})
        with patch.object(authed_client._session, "post", return_value=resp):
            result = authed_client.move_to_trash_bin("abc")
        assert result["status"] == 200

    def test_create_speaker(self, authed_client):
        resp = self._mock_response(json_data={"speaker": {"id": "s1"}})
        with patch.object(authed_client._session, "post", return_value=resp):
            result = authed_client.create_speaker("John")
        assert result["status"] == 200

    def test_set_transcript_speaker(self, authed_client):
        resp = self._mock_response(json_data={})
        with patch.object(authed_client._session, "get", return_value=resp):
            result = authed_client.set_transcript_speaker(
                "sid", "uuid", "spkid", "John"
            )
        assert result["status"] == 200

    def test_get_notification_settings(self, authed_client):
        resp = self._mock_response(json_data={"settings": {}})
        with patch.object(authed_client._session, "get", return_value=resp):
            result = authed_client.get_notification_settings()
        assert result["status"] == 200

    def test_list_groups(self, authed_client):
        resp = self._mock_response(json_data=[{"id": "g1", "name": "Eng"}])
        with patch.object(authed_client._session, "get", return_value=resp):
            result = authed_client.list_groups()
        assert result["status"] == 200

    def test_get_folders(self, authed_client):
        resp = self._mock_response(json_data={"folders": []})
        with patch.object(authed_client._session, "get", return_value=resp):
            result = authed_client.get_folders()
        assert result["status"] == 200

    def test_create_folder(self, authed_client):
        resp = self._mock_response(json_data={"folder": {"id": "f1"}})
        with patch.object(authed_client._session, "post", return_value=resp):
            result = authed_client.create_folder("Work")
        assert result["status"] == 200

    def test_rename_folder(self, authed_client):
        resp = self._mock_response(json_data={})
        with patch.object(authed_client._session, "post", return_value=resp):
            result = authed_client.rename_folder("f1", "New Name")
        assert result["status"] == 200

    def test_add_folder_speeches(self, authed_client):
        resp = self._mock_response(json_data={})
        with patch.object(authed_client._session, "post", return_value=resp):
            result = authed_client.add_folder_speeches("f1", ["s1", "s2"])
        assert result["status"] == 200

    def test_add_folder_speeches_single_string(self, authed_client):
        """Test that a single string speech_id gets wrapped in a list."""
        resp = self._mock_response(json_data={})
        with patch.object(authed_client._session, "post", return_value=resp):
            result = authed_client.add_folder_speeches("f1", "s1")
        assert result["status"] == 200

    def test_download_speech_success(self, authed_client):
        resp = self._mock_response(json_data={})
        resp.ok = True
        resp.content = b"file content"
        with patch.object(authed_client._session, "post", return_value=resp):
            with patch("builtins.open", mock_open()):
                result = authed_client.download_speech("abc", fileformat="txt")
        assert result["data"]["filename"] == "abc.txt"

    def test_download_speech_with_name(self, authed_client):
        resp = self._mock_response(json_data={})
        resp.ok = True
        resp.content = b"file content"
        with patch.object(authed_client._session, "post", return_value=resp):
            with patch("builtins.open", mock_open()):
                result = authed_client.download_speech(
                    "abc", name="output", fileformat="pdf"
                )
        assert result["data"]["filename"] == "output.pdf"

    def test_download_speech_multi_format_zip(self, authed_client):
        resp = self._mock_response(json_data={})
        resp.ok = True
        resp.content = b"zip content"
        with patch.object(authed_client._session, "post", return_value=resp):
            with patch("builtins.open", mock_open()):
                result = authed_client.download_speech(
                    "abc", fileformat="txt,pdf"
                )
        assert result["data"]["filename"] == "abc.zip"

    def test_download_speech_failure(self, authed_client):
        resp = self._mock_response(status=500)
        resp.ok = False
        with patch.object(authed_client._session, "post", return_value=resp):
            with pytest.raises(OtterAIError, match="Got response status 500"):
                authed_client.download_speech("abc")
