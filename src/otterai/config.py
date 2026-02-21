"""
Configuration and credential management for OtterAI CLI.

Credential precedence:
  1. Environment variables (OTTERAI_USERNAME + OTTERAI_PASSWORD)
  2. System keyring (via `keyring` library)
  3. Config file (~/.otterai/config.json) — legacy fallback

Set OTTERAI_CONFIG_DIR to override the default config directory.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import keyring
import keyring.errors

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_DIR = Path.home() / ".otterai"
_KEYRING_SERVICE = "otterai-cli"


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


def _check_keyring() -> Optional[tuple[str, str]]:
    """Read credentials from keyring, or None if unavailable/empty."""
    try:
        kr_user = keyring.get_password(_KEYRING_SERVICE, "username")
        kr_pass = keyring.get_password(_KEYRING_SERVICE, "password")
        if kr_user is not None and kr_pass is not None:
            return kr_user, kr_pass
    except Exception as exc:
        logger.debug("Keyring read failed: %s", exc)
    return None


def _check_file() -> Optional[tuple[Optional[str], Optional[str]]]:
    """Read credentials from config file, or None if unavailable."""
    config_file = _get_config_file()
    if config_file.exists():
        try:
            data = json.loads(config_file.read_text())
            return data.get("username"), data.get("password")
        except (json.JSONDecodeError, AttributeError, TypeError, OSError) as exc:
            logger.debug("Config file read failed: %s", exc)
    return None


def save_credentials(username: str, password: str) -> str:
    """
    Save credentials, preferring the system keyring.

    Returns:
        "keyring" if stored in keyring, "file" if stored in config file.
    """
    try:
        keyring.set_password(_KEYRING_SERVICE, "username", username)
        try:
            keyring.set_password(_KEYRING_SERVICE, "password", password)
        except Exception:
            # Roll back the username write to avoid orphaned partial state
            try:
                keyring.delete_password(_KEYRING_SERVICE, "username")
            except Exception:
                pass
            raise
        return "keyring"
    except Exception as exc:
        logger.debug("Keyring write failed, falling back to file: %s", exc)

    # Fallback to config file
    _ensure_config_dir()
    config_file = _get_config_file()
    config = {"username": username, "password": password}
    config_file.write_text(json.dumps(config, indent=2))
    config_file.chmod(0o600)
    return "file"


def load_credentials() -> tuple[Optional[str], Optional[str]]:
    """
    Load credentials from environment variables, keyring, or config file.

    Returns:
        Tuple of (username, password), either may be None if not found.
    """
    # 1. Check environment variables first
    username = os.getenv("OTTERAI_USERNAME")
    password = os.getenv("OTTERAI_PASSWORD")

    if username and password:
        return username, password

    # 2. Check system keyring
    kr = _check_keyring()
    if kr is not None:
        return kr

    # 3. Fall back to config file
    result = _check_file()
    if result is not None:
        return result

    return None, None


def clear_credentials() -> bool:
    """
    Clear saved credentials from keyring and config file.

    Returns:
        True if credentials were cleared from either source, False if none existed.
    """
    cleared = False

    # Clear from keyring
    for key in ("username", "password"):
        try:
            keyring.delete_password(_KEYRING_SERVICE, key)
            cleared = True
        except Exception as exc:
            logger.debug("Keyring delete '%s' failed: %s", key, exc)

    # Clear config file (legacy)
    config_file = _get_config_file()
    if config_file.exists():
        config_file.unlink()
        cleared = True

    return cleared


def get_credential_backend() -> Optional[str]:
    """
    Detect which backend currently holds credentials.

    Returns:
        "environment", "keyring", "file", or None.
    """
    username = os.getenv("OTTERAI_USERNAME")
    password = os.getenv("OTTERAI_PASSWORD")
    if username and password:
        return "environment"

    if _check_keyring() is not None:
        return "keyring"

    result = _check_file()
    if result is not None:
        u, p = result
        if u and p:
            return "file"

    return None


def get_config_path() -> Path:
    """Return the path to the config file."""
    return _get_config_file()
