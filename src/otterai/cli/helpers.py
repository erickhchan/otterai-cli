import click
from datetime import datetime, timedelta, timezone

from ..client import OtterAIClient
from ..config import load_credentials


def _format_timestamp(epoch: int, fmt: str = "%a %b %d, %Y @ %I:%M%p ET") -> str:
    """Convert epoch timestamp to human-readable string (US Eastern)."""
    if not epoch:
        return ""
    try:
        from zoneinfo import ZoneInfo

        dt = datetime.fromtimestamp(epoch, tz=ZoneInfo("America/New_York"))
    except ImportError:
        # Python < 3.9 fallback: assume UTC-5
        dt = datetime.fromtimestamp(epoch, tz=timezone(timedelta(hours=-5)))
    return dt.strftime(fmt)


def _format_duration(seconds: int) -> str:
    """Convert seconds to human-readable duration."""
    if not seconds:
        return "0s"
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining = minutes % 60
    return f"{hours}h {remaining}m"


def _resolve_folder_id(client: OtterAIClient, folder_ref: str) -> str:
    """Resolve a folder reference to an ID.

    Accepts a numeric folder ID or a folder name (case-insensitive match).
    """
    if folder_ref.isdigit():
        return folder_ref

    result = client.get_folders()
    if result["status"] != 200:
        raise click.ClickException(f"Failed to list folders: {result}")

    folders = result["data"].get("folders", [])
    for f in folders:
        if f.get("folder_name", "").lower() == folder_ref.lower():
            return str(f["id"])

    raise click.ClickException(
        f"Folder '{folder_ref}' not found. Use 'otter folders list' to see available folders."
    )


def get_authenticated_client() -> OtterAIClient:
    """Get an authenticated OtterAIClient."""
    username, password = load_credentials()
    if not username or not password:
        raise click.ClickException("Not logged in. Run 'otter login' first.")

    client = OtterAIClient()
    result = client.login(username, password)
    if result["status"] != 200:
        raise click.ClickException(f"Login failed: {result}")

    return client
