import click
from datetime import datetime

from ..client import OtterAIClient
from ..config import load_credentials


def _format_timestamp(epoch: int, fmt: str = "%a %b %d, %Y @ %I:%M%p") -> str:
    """Convert epoch timestamp to human-readable string in local timezone."""
    if not epoch:
        return ""
    dt = datetime.fromtimestamp(epoch).astimezone()
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


def format_speech_markdown(data: dict) -> str:
    """Format a get_speech() response as a Markdown document.

    Parameters
    ----------
    data : dict
        The ``result["data"]`` dict from ``client.get_speech()``.
        Contains ``speech`` (dict) and optionally ``transcripts`` (list).
    """
    speech = data.get("speech", {})

    title = speech.get("title") or "Untitled"
    created = speech.get("created_at", 0)
    duration = speech.get("duration", 0)
    speakers = [
        s.get("speaker_name", "")
        for s in speech.get("speakers", [])
        if s.get("speaker_name")
    ]

    lines = [f"# {title}", ""]

    if created:
        lines.append(f"**Date:** {_format_timestamp(created)}")
    if duration:
        lines.append(f"**Duration:** {_format_duration(duration)}")

    folder_info = speech.get("folder")
    if isinstance(folder_info, dict) and folder_info.get("folder_name"):
        lines.append(f"**Folder:** {folder_info['folder_name']}")

    if speakers:
        lines.append(f"**Speakers:** {', '.join(speakers)}")

    # Support both nested and top-level transcript locations
    transcripts = speech.get("transcripts") or data.get("transcripts", [])
    if transcripts:
        lines.append("")
        lines.append("---")
        lines.append("")
        for t in transcripts:
            speaker = t.get("speaker_name", "Unknown")
            text = t.get("transcript", "")
            lines.append(f"**{speaker}:** {text}")
            lines.append("")

    return "\n".join(lines) + "\n"


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
