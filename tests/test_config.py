"""Tests for otterai.config credential management."""

import json

from otterai import config


class TestGetConfigPath:
    """Tests for get_config_path / internal path helpers."""

    def test_returns_path_in_config_dir(self, temp_config_dir):
        path = config.get_config_path()
        assert path.parent == temp_config_dir
        assert path.name == "config.json"

    def test_respects_otterai_config_dir_env_var(self, tmp_path, monkeypatch):
        custom = tmp_path / "custom-dir"
        monkeypatch.setenv("OTTERAI_CONFIG_DIR", str(custom))
        assert config.get_config_path() == custom / "config.json"

    def test_defaults_to_home_dotdir_without_env_var(self, monkeypatch):
        monkeypatch.delenv("OTTERAI_CONFIG_DIR", raising=False)
        from pathlib import Path

        expected = Path.home() / ".otterai" / "config.json"
        assert config.get_config_path() == expected


class TestSaveCredentials:
    """Tests for save_credentials."""

    def test_saves_to_keyring_when_available(self, temp_config_dir, fake_keyring):
        backend = config.save_credentials("alice", "s3cret")
        assert backend == "keyring"
        assert fake_keyring[("otterai-cli", "username")] == "alice"
        assert fake_keyring[("otterai-cli", "password")] == "s3cret"

    def test_does_not_write_file_when_keyring_succeeds(self, temp_config_dir, fake_keyring):
        config.save_credentials("alice", "s3cret")
        config_file = temp_config_dir / "config.json"
        assert not config_file.exists()

    def test_falls_back_to_file_when_keyring_broken(self, temp_config_dir, broken_keyring):
        backend = config.save_credentials("alice", "s3cret")
        assert backend == "file"
        config_file = temp_config_dir / "config.json"
        assert config_file.exists()
        data = json.loads(config_file.read_text())
        assert data == {"username": "alice", "password": "s3cret"}

    def test_file_fallback_sets_restrictive_permissions(self, temp_config_dir, broken_keyring):
        config.save_credentials("alice", "s3cret")
        config_file = temp_config_dir / "config.json"
        file_mode = config_file.stat().st_mode & 0o777
        assert file_mode == 0o600

    def test_creates_config_dir_if_missing(self, tmp_path, monkeypatch, broken_keyring):
        nested = tmp_path / "nonexistent"
        monkeypatch.setenv("OTTERAI_CONFIG_DIR", str(nested))
        monkeypatch.delenv("OTTERAI_USERNAME", raising=False)
        monkeypatch.delenv("OTTERAI_PASSWORD", raising=False)

        config.save_credentials("alice", "s3cret")
        assert nested.is_dir()
        assert (nested / "config.json").exists()

    def test_config_dir_has_700_permissions(self, tmp_path, monkeypatch, broken_keyring):
        nested = tmp_path / "new-dir"
        monkeypatch.setenv("OTTERAI_CONFIG_DIR", str(nested))
        config.save_credentials("alice", "s3cret")
        dir_mode = nested.stat().st_mode & 0o777
        assert dir_mode == 0o700

    def test_overwrites_existing_credentials(self, temp_config_dir, fake_keyring):
        config.save_credentials("alice", "old-pass")
        config.save_credentials("bob", "new-pass")
        assert fake_keyring[("otterai-cli", "username")] == "bob"
        assert fake_keyring[("otterai-cli", "password")] == "new-pass"

    def test_handles_special_characters(self, temp_config_dir, fake_keyring):
        username = "user@example.com"
        password = 'p@ss"w0rd!$#&\n\t'
        config.save_credentials(username, password)
        assert fake_keyring[("otterai-cli", "username")] == username
        assert fake_keyring[("otterai-cli", "password")] == password

    def test_file_fallback_json_is_pretty_printed(self, temp_config_dir, broken_keyring):
        config.save_credentials("alice", "pass")
        raw = (temp_config_dir / "config.json").read_text()
        assert "\n" in raw
        assert "  " in raw

    def test_partial_keyring_failure_rolls_back_and_falls_back(
        self, temp_config_dir, partial_keyring_write
    ):
        """If password write fails after username write, username is cleaned up."""
        backend = config.save_credentials("alice", "s3cret")
        assert backend == "file"
        # Orphaned username should have been rolled back
        assert ("otterai-cli", "username") not in partial_keyring_write
        # Credentials should be in file
        config_file = temp_config_dir / "config.json"
        data = json.loads(config_file.read_text())
        assert data == {"username": "alice", "password": "s3cret"}


class TestLoadCredentials:
    """Tests for load_credentials."""

    def test_loads_from_keyring(self, temp_config_dir, fake_keyring):
        fake_keyring[("otterai-cli", "username")] = "kr-user"
        fake_keyring[("otterai-cli", "password")] = "kr-pass"
        username, password = config.load_credentials()
        assert username == "kr-user"
        assert password == "kr-pass"

    def test_returns_none_tuple_when_no_config(self, temp_config_dir):
        username, password = config.load_credentials()
        assert username is None
        assert password is None

    def test_env_vars_take_precedence_over_keyring(self, temp_config_dir, fake_keyring, monkeypatch):
        fake_keyring[("otterai-cli", "username")] = "kr-user"
        fake_keyring[("otterai-cli", "password")] = "kr-pass"
        monkeypatch.setenv("OTTERAI_USERNAME", "env-user")
        monkeypatch.setenv("OTTERAI_PASSWORD", "env-pass")
        username, password = config.load_credentials()
        assert username == "env-user"
        assert password == "env-pass"

    def test_keyring_takes_precedence_over_file(self, temp_config_dir, fake_keyring):
        # Write to config file directly (legacy)
        config_file = temp_config_dir / "config.json"
        config_file.write_text(json.dumps({"username": "file-user", "password": "file-pass"}))
        # Also put in keyring
        fake_keyring[("otterai-cli", "username")] = "kr-user"
        fake_keyring[("otterai-cli", "password")] = "kr-pass"
        username, password = config.load_credentials()
        assert username == "kr-user"
        assert password == "kr-pass"

    def test_falls_back_to_file_when_keyring_empty(self, temp_config_dir):
        """Credentials in file are loaded when keyring is available but empty."""
        config_file = temp_config_dir / "config.json"
        config_file.write_text(json.dumps({"username": "file-user", "password": "file-pass"}))
        username, password = config.load_credentials()
        assert username == "file-user"
        assert password == "file-pass"

    def test_falls_back_to_file_when_keyring_broken(self, temp_config_dir, broken_keyring):
        config_file = temp_config_dir / "config.json"
        config_file.write_text(json.dumps({"username": "file-user", "password": "file-pass"}))
        username, password = config.load_credentials()
        assert username == "file-user"
        assert password == "file-pass"

    def test_partial_keyring_falls_back_to_file(self, temp_config_dir, fake_keyring):
        """Only username in keyring (no password) should fall through to file."""
        fake_keyring[("otterai-cli", "username")] = "kr-user"
        # No password in keyring
        config_file = temp_config_dir / "config.json"
        config_file.write_text(
            json.dumps({"username": "file-user", "password": "file-pass"})
        )
        username, password = config.load_credentials()
        assert username == "file-user"
        assert password == "file-pass"

    def test_unreadable_config_file_returns_none_tuple(self, temp_config_dir):
        """OSError from read_text() is handled gracefully."""
        config_file = temp_config_dir / "config.json"
        config_file.write_text('{"username": "u", "password": "p"}')
        config_file.chmod(0o000)
        username, password = config.load_credentials()
        assert username is None
        assert password is None
        # Restore permissions for cleanup
        config_file.chmod(0o600)

    def test_falls_back_to_file_when_only_username_env_set(
        self, saved_credentials, monkeypatch
    ):
        """When only one env var is set, both must be present to use env vars."""
        monkeypatch.setenv("OTTERAI_USERNAME", "env-user")
        username, password = config.load_credentials()
        # Falls back to keyring because both env vars are required
        assert username == "testuser"
        assert password == "testpass"

    def test_falls_back_to_file_when_only_password_env_set(
        self, saved_credentials, monkeypatch
    ):
        monkeypatch.setenv("OTTERAI_PASSWORD", "env-pass")
        username, password = config.load_credentials()
        assert username == "testuser"
        assert password == "testpass"

    def test_corrupted_json_returns_none_tuple(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text("{this is not valid json!!!")
        username, password = config.load_credentials()
        assert username is None
        assert password is None

    def test_empty_file_returns_none_tuple(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text("")
        username, password = config.load_credentials()
        assert username is None
        assert password is None

    def test_json_array_instead_of_object_returns_none_tuple(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text('["not", "an", "object"]')
        username, password = config.load_credentials()
        assert username is None
        assert password is None

    def test_json_with_missing_keys_returns_none_values(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text('{"unrelated_key": "value"}')
        username, password = config.load_credentials()
        assert username is None
        assert password is None

    def test_json_with_only_username_returns_none_password(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text('{"username": "alice"}')
        username, password = config.load_credentials()
        assert username == "alice"
        assert password is None

    def test_json_null_value_returns_none(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text('{"username": null, "password": null}')
        username, password = config.load_credentials()
        assert username is None
        assert password is None

    def test_env_vars_with_empty_strings_fall_back(
        self, saved_credentials, monkeypatch
    ):
        """Empty env var strings are falsy, so should fall back."""
        monkeypatch.setenv("OTTERAI_USERNAME", "")
        monkeypatch.setenv("OTTERAI_PASSWORD", "")
        username, password = config.load_credentials()
        assert username == "testuser"
        assert password == "testpass"


class TestClearCredentials:
    """Tests for clear_credentials."""

    def test_removes_from_keyring(self, saved_credentials, fake_keyring):
        assert ("otterai-cli", "username") in fake_keyring
        result = config.clear_credentials()
        assert result is True
        assert ("otterai-cli", "username") not in fake_keyring
        assert ("otterai-cli", "password") not in fake_keyring

    def test_removes_config_file_too(self, temp_config_dir, fake_keyring):
        """Clear removes legacy config file even if keyring is empty."""
        config_file = temp_config_dir / "config.json"
        config_file.write_text('{"username": "u", "password": "p"}')
        result = config.clear_credentials()
        assert result is True
        assert not config_file.exists()

    def test_clears_both_keyring_and_file(self, temp_config_dir, fake_keyring):
        fake_keyring[("otterai-cli", "username")] = "kr-user"
        fake_keyring[("otterai-cli", "password")] = "kr-pass"
        config_file = temp_config_dir / "config.json"
        config_file.write_text('{"username": "u", "password": "p"}')

        result = config.clear_credentials()
        assert result is True
        assert ("otterai-cli", "username") not in fake_keyring
        assert not config_file.exists()

    def test_returns_false_when_nothing_exists(self, temp_config_dir):
        result = config.clear_credentials()
        assert result is False

    def test_clears_file_when_keyring_broken(self, temp_config_dir, broken_keyring):
        config_file = temp_config_dir / "config.json"
        config_file.write_text('{"username": "u", "password": "p"}')
        result = config.clear_credentials()
        assert result is True
        assert not config_file.exists()

    def test_can_save_after_clear(self, saved_credentials, fake_keyring):
        config.clear_credentials()
        config.save_credentials("new-user", "new-pass")
        username, password = config.load_credentials()
        assert username == "new-user"
        assert password == "new-pass"

    def test_clear_twice_returns_false_second_time(self, saved_credentials):
        assert config.clear_credentials() is True
        assert config.clear_credentials() is False

    def test_load_returns_none_after_clear(self, saved_credentials):
        config.clear_credentials()
        username, password = config.load_credentials()
        assert username is None
        assert password is None


class TestGetCredentialBackend:
    """Tests for get_credential_backend."""

    def test_returns_environment_when_env_vars_set(self, temp_config_dir, monkeypatch):
        monkeypatch.setenv("OTTERAI_USERNAME", "env-user")
        monkeypatch.setenv("OTTERAI_PASSWORD", "env-pass")
        assert config.get_credential_backend() == "environment"

    def test_returns_keyring_when_in_keyring(self, temp_config_dir, fake_keyring):
        fake_keyring[("otterai-cli", "username")] = "kr-user"
        fake_keyring[("otterai-cli", "password")] = "kr-pass"
        assert config.get_credential_backend() == "keyring"

    def test_returns_file_when_in_config_file(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text(json.dumps({"username": "u", "password": "p"}))
        assert config.get_credential_backend() == "file"

    def test_returns_none_when_no_credentials(self, temp_config_dir):
        assert config.get_credential_backend() is None

    def test_environment_takes_precedence(self, temp_config_dir, fake_keyring, monkeypatch):
        fake_keyring[("otterai-cli", "username")] = "kr-user"
        fake_keyring[("otterai-cli", "password")] = "kr-pass"
        monkeypatch.setenv("OTTERAI_USERNAME", "env-user")
        monkeypatch.setenv("OTTERAI_PASSWORD", "env-pass")
        assert config.get_credential_backend() == "environment"

    def test_keyring_takes_precedence_over_file(self, temp_config_dir, fake_keyring):
        fake_keyring[("otterai-cli", "username")] = "kr-user"
        fake_keyring[("otterai-cli", "password")] = "kr-pass"
        config_file = temp_config_dir / "config.json"
        config_file.write_text(json.dumps({"username": "u", "password": "p"}))
        assert config.get_credential_backend() == "keyring"

    def test_returns_file_when_keyring_broken(self, temp_config_dir, broken_keyring):
        config_file = temp_config_dir / "config.json"
        config_file.write_text(json.dumps({"username": "u", "password": "p"}))
        assert config.get_credential_backend() == "file"

    def test_returns_none_when_file_has_empty_strings(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text(json.dumps({"username": "", "password": ""}))
        assert config.get_credential_backend() is None

    def test_returns_none_when_file_unreadable(self, temp_config_dir):
        config_file = temp_config_dir / "config.json"
        config_file.write_text(json.dumps({"username": "u", "password": "p"}))
        config_file.chmod(0o000)
        assert config.get_credential_backend() is None
        config_file.chmod(0o600)


class TestRoundTrip:
    """Integration tests exercising save -> load -> clear cycles."""

    def test_save_then_load(self, temp_config_dir):
        config.save_credentials("roundtrip-user", "roundtrip-pass")
        username, password = config.load_credentials()
        assert username == "roundtrip-user"
        assert password == "roundtrip-pass"

    def test_save_load_clear_load(self, temp_config_dir):
        config.save_credentials("user1", "pass1")
        assert config.load_credentials() == ("user1", "pass1")

        assert config.clear_credentials() is True
        assert config.load_credentials() == (None, None)

    def test_multiple_save_overwrite_cycle(self, temp_config_dir):
        for i in range(5):
            config.save_credentials(f"user{i}", f"pass{i}")
        username, password = config.load_credentials()
        assert username == "user4"
        assert password == "pass4"

    def test_config_path_matches_actual_file(self, temp_config_dir, broken_keyring):
        """When keyring is broken, credentials go to file which should match config_path."""
        config.save_credentials("alice", "pass")
        path = config.get_config_path()
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["username"] == "alice"
