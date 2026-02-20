"""
Configuration and credential management for OtterAI CLI.

Credentials are stored in ~/.otterai/config.json and can be
overridden with environment variables OTTERAI_USERNAME and OTTERAI_PASSWORD.
"""

import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".otterai"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _ensure_config_dir() -> None:
    """Create config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(mode=0o700, exist_ok=True)


def save_credentials(username: str, password: str) -> None:
    """Save credentials to config file."""
    _ensure_config_dir()
    config = {"username": username, "password": password}
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    CONFIG_FILE.chmod(0o600)


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
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text())
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
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()
        return True
    return False


def get_config_path() -> Path:
    """Return the path to the config file."""
    return CONFIG_FILE
