"""Tests for the config module."""

import os
from unittest.mock import patch

from otterai import config


def test_save_and_load_credentials(temp_config_dir):
    """Test saving and loading credentials."""
    config.save_credentials("testuser", "testpass")

    username, password = config.load_credentials()
    assert username == "testuser"
    assert password == "testpass"


def test_load_credentials_from_env(temp_config_dir):
    """Test that environment variables take precedence."""
    config.save_credentials("fileuser", "filepass")

    with patch.dict(
        os.environ, {"OTTERAI_USERNAME": "envuser", "OTTERAI_PASSWORD": "envpass"}
    ):
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
