"""
Configuration and credential management for OtterAI CLI.

Credentials are stored in ~/.otterai/config.json and can be
overridden with environment variables OTTERAI_USERNAME and OTTERAI_PASSWORD.

Set OTTERAI_CONFIG_DIR to override the default config directory.
"""

import json
import os
from pathlib import Path
from typing import Optional

_DEFAULT_CONFIG_DIR = Path.home() / ".otterai"


def _get_config_dir() -> Path:
    """Return the config directory, respecting OTTERAI_CONFIG_DIR env var."""
    override = os.getenv("OTTERAI_CONFIG_DIR")
    if override:
        return Path(override)
    return _DEFAULT_CONFIG_DIR


def _get_config_file() -> Path:
    """Return the config file path."""
    return _get_config_dir() / "config.json"


def _ensure_config_dir() -> None:
    """Create config directory if it doesn't exist."""
    _get_config_dir().mkdir(mode=0o700, exist_ok=True)


def save_credentials(username: str, password: str) -> None:
    """Save credentials to config file."""
    _ensure_config_dir()
    config_file = _get_config_file()
    config = {"username": username, "password": password}
    config_file.write_text(json.dumps(config, indent=2))
    config_file.chmod(0o600)


def load_credentials() -> tuple[Optional[str], Optional[str]]:
    """
    Load credentials from environment variables or config file.

    Environment variables take precedence over config file.

    Returns:
        Tuple of (username, password), either may be None if not found.
    """
    # Check environment variables first
    username = os.getenv("OTTERAI_USERNAME")
    password = os.getenv("OTTERAI_PASSWORD")

    if username and password:
        return username, password

    # Fall back to config file
    config_file = _get_config_file()
    if config_file.exists():
        try:
            config = json.loads(config_file.read_text())
            return config.get("username"), config.get("password")
        except (json.JSONDecodeError, AttributeError, TypeError):
            return None, None

    return None, None


def clear_credentials() -> bool:
    """
    Clear saved credentials.

    Returns:
        True if credentials were cleared, False if no config existed.
    """
    config_file = _get_config_file()
    if config_file.exists():
        config_file.unlink()
        return True
    return False


def get_config_path() -> Path:
    """Return the path to the config file."""
    return _get_config_file()
