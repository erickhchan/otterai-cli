import click
from datetime import datetime, timezone

from ..client import OtterAIClient
from ..config import load_credentials

FRONTMATTER_AVAILABLE_FIELDS = (
    "title",
    "summary",
    "speakers",
    "start_time",
    "end_time",
    "duration_seconds",
    "source",
    "speech_id",
    "folder",
    "folder_id",
    "otid",
    "created_at",
    "transcript_updated_at",
    "language",
    "transcript_count",
    "process_status",
)

FRONTMATTER_DEFAULT_FIELDS = (
    "title",
    "summary",
    "speakers",
    "start_time",
    "end_time",
    "duration_seconds",
    "source",
    "speech_id",
    "folder",
    "folder_id",
)


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


def _format_timestamp_iso(epoch: int) -> str:
    """Convert epoch timestamp to ISO-8601 string in UTC."""
    if not epoch:
        return ""
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _yaml_quote(value: str) -> str:
    """Quote YAML strings so spaces/special chars are safe for frontmatter."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _yaml_scalar(value) -> str:
    """Render a YAML scalar value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return _yaml_quote(str(value))


def _normalize_frontmatter_fields(
    frontmatter_fields: list[str] | None = None,
) -> list[str]:
    """Validate and normalize frontmatter fields."""
    fields = (
        list(FRONTMATTER_DEFAULT_FIELDS)
        if frontmatter_fields is None
        else [f.strip() for f in frontmatter_fields if f and f.strip()]
    )
    unknown = [f for f in fields if f not in FRONTMATTER_AVAILABLE_FIELDS]
    if unknown:
        raise ValueError(
            f"Unknown frontmatter field(s): {', '.join(unknown)}. "
            f"Available: {', '.join(FRONTMATTER_AVAILABLE_FIELDS)}"
        )
    seen = set()
    deduped = []
    for f in fields:
        if f not in seen:
            deduped.append(f)
            seen.add(f)
    return deduped


def parse_frontmatter_fields(fields_spec: str | None) -> list[str]:
    """Parse CLI field specification into an ordered list."""
    if fields_spec is None:
        return list(FRONTMATTER_DEFAULT_FIELDS)
    spec = fields_spec.strip()
    if not spec or spec.lower() == "default":
        return list(FRONTMATTER_DEFAULT_FIELDS)
    if spec.lower() == "none":
        return []
    return _normalize_frontmatter_fields(spec.split(","))


def _add_frontmatter_scalar(lines: list[str], key: str, value) -> None:
    if value in (None, ""):
        return
    lines.append(f"{key}: {_yaml_scalar(value)}")


def _add_frontmatter_list(lines: list[str], key: str, values: list) -> None:
    clean_values = [v for v in values if v not in (None, "")]
    if not clean_values:
        return
    lines.append(f"{key}:")
    for value in clean_values:
        lines.append(f"  - {_yaml_scalar(value)}")


def _add_frontmatter_dict(lines: list[str], key: str, value: dict) -> None:
    if not isinstance(value, dict):
        return
    clean_items = {k: v for k, v in value.items() if v not in (None, "")}
    if not clean_items:
        return
    lines.append(f"{key}:")
    for k, v in clean_items.items():
        lines.append(f"  {k}: {_yaml_scalar(v)}")


def _add_frontmatter_field(lines: list[str], key: str, value) -> None:
    if isinstance(value, list):
        _add_frontmatter_list(lines, key, value)
    elif isinstance(value, dict):
        _add_frontmatter_dict(lines, key, value)
    else:
        _add_frontmatter_scalar(lines, key, value)


def _extract_frontmatter_values(data: dict) -> dict:
    """Extract normalized values used for YAML frontmatter."""
    speech = data.get("speech", {})
    title = speech.get("title") or "Untitled"
    created = speech.get("created_at", 0)
    start_time = speech.get("start_time", 0)
    end_time = speech.get("end_time", 0)
    updated = speech.get("transcript_updated_at", 0)
    duration = speech.get("duration", 0)
    speakers = [
        s.get("speaker_name", "").strip()
        for s in speech.get("speakers", [])
        if s.get("speaker_name", "").strip()
    ]
    folder_info = speech.get("folder")
    folder_name = (
        folder_info.get("folder_name")
        if isinstance(folder_info, dict)
        else None
    )
    folder_id = folder_info.get("id") if isinstance(folder_info, dict) else None
    transcripts = speech.get("transcripts") or data.get("transcripts", [])

    return {
        "title": title,
        "summary": speech.get("summary"),
        "speakers": speakers,
        "start_time": _format_timestamp_iso(start_time),
        "end_time": _format_timestamp_iso(end_time),
        "duration_seconds": duration if duration else None,
        "source": "otter.ai",
        "speech_id": speech.get("speech_id"),
        "folder": folder_name,
        "folder_id": folder_id,
        "otid": speech.get("otid"),
        "created_at": _format_timestamp_iso(created),
        "transcript_updated_at": _format_timestamp_iso(updated),
        "language": speech.get("language"),
        "transcript_count": len(transcripts) if transcripts else None,
        "process_status": speech.get("process_status"),
    }


def _speaker_names_by_id(speech: dict) -> dict[str, str]:
    """Build a lookup for transcript speaker_id values."""
    speaker_names = {}
    for speaker in speech.get("speakers", []):
        speaker_id = speaker.get("id", speaker.get("speaker_id"))
        if speaker_id in (None, ""):
            continue
        name = speaker.get("speaker_name")
        if isinstance(name, str) and name.strip():
            speaker_names[str(speaker_id)] = name.strip()
    return speaker_names


def _resolve_transcript_speaker(
    transcript: dict,
    speaker_names: dict[str, str] | None = None,
) -> str:
    speaker = transcript.get("speaker_name")
    if isinstance(speaker, str) and speaker.strip():
        return speaker.strip()

    speaker_id = transcript.get("speaker_id")
    if speaker_id not in (None, "") and speaker_names:
        speaker = speaker_names.get(str(speaker_id))
        if speaker:
            return speaker

    speaker = transcript.get("speaker_model_label")
    if isinstance(speaker, str) and speaker.strip():
        return speaker.strip()

    return "Unknown"


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


def format_speech_markdown(
    data: dict,
    frontmatter_fields: list[str] | None = None,
) -> str:
    """Format a get_speech() response as a Markdown document.

    Parameters
    ----------
    data : dict
        The ``result["data"]`` dict from ``client.get_speech()``.
        Contains ``speech`` (dict) and optionally ``transcripts`` (list).
    """
    speech = data.get("speech", {})
    title = speech.get("title") or "Untitled"
    # Support both nested and top-level transcript locations
    transcripts = speech.get("transcripts") or data.get("transcripts", [])
    speaker_names = _speaker_names_by_id(speech)

    selected_fields = _normalize_frontmatter_fields(frontmatter_fields)
    field_values = _extract_frontmatter_values(data)

    frontmatter = []
    for field in selected_fields:
        _add_frontmatter_field(frontmatter, field, field_values.get(field))

    lines = ["---", *frontmatter, "---", "", f"# {title}", ""]

    if transcripts:
        lines.append("## Transcript")
        lines.append("")
        for t in transcripts:
            speaker = _resolve_transcript_speaker(t, speaker_names)
            text = (t.get("transcript") or "").strip()
            if not text:
                continue
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
