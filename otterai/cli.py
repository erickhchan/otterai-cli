"""
Command-line interface for OtterAI.

Usage:
    otter login
    otter speeches list
    otter speeches download <speech_id>
    otter speakers list

NOTE: Otter.ai speeches have two IDs:
  - speech_id (e.g. 22WB27HAEBEJYFCA) — internal, does NOT work with API calls
  - otid (e.g. jqb7OHo6mrHtCuMkyLN0nUS8mxY) — the ID used in all API endpoints

All CLI commands that accept a SPEECH_ID expect the otid value.
Use `otter speeches list` or `otter speeches list --json` to find otids.
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone

import click

from .config import clear_credentials, get_config_path, load_credentials, save_credentials
from .otterai import OtterAI, OtterAIException


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


def _resolve_folder_id(client: "OtterAI", folder_ref: str) -> str:
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


def get_authenticated_client() -> OtterAI:
    """Get an authenticated OtterAI client."""
    username, password = load_credentials()
    if not username or not password:
        raise click.ClickException("Not logged in. Run 'otter login' first.")

    client = OtterAI()
    result = client.login(username, password)
    if result["status"] != 200:
        raise click.ClickException(f"Login failed: {result}")

    return client


@click.group()
@click.version_option(version="0.1.0", prog_name="otter")
def main():
    """OtterAI CLI - Interact with Otter.ai from the command line."""
    pass


# =============================================================================
# Authentication Commands
# =============================================================================


@main.command()
@click.option("--username", "-u", prompt=True, help="Otter.ai username (email)")
@click.option(
    "--password", "-p", prompt=True, hide_input=True, help="Otter.ai password"
)
def login(username: str, password: str):
    """Authenticate with Otter.ai and save credentials."""
    client = OtterAI()
    result = client.login(username, password)

    if result["status"] != 200:
        click.echo(f"Login failed: {result.get('data', {})}", err=True)
        sys.exit(1)

    save_credentials(username, password)
    user_data = result.get("data", {})
    click.echo(f"Logged in as {user_data.get('email', username)}")
    click.echo(f"Credentials saved to {get_config_path()}")


@main.command()
def logout():
    """Clear saved credentials."""
    if clear_credentials():
        click.echo("Credentials cleared.")
    else:
        click.echo("No saved credentials found.")


@main.command()
def user():
    """Show current user information."""
    client = get_authenticated_client()
    result = client.get_user()

    if result["status"] != 200:
        click.echo(f"Failed to get user: {result}", err=True)
        sys.exit(1)

    click.echo(json.dumps(result["data"], indent=2))


# =============================================================================
# Speeches Commands
# =============================================================================


@main.group()
def speeches():
    """Manage speeches (transcripts)."""
    pass


@speeches.command("list")
@click.option("--folder", "-f", default=0, help="Folder ID or name (default: 0 = all)")
@click.option("--page-size", "-n", default=45, help="Number of results (default: 45)")
@click.option(
    "--source",
    "-s",
    default="owned",
    type=click.Choice(["owned", "shared", "all"]),
    help="Source filter (default: owned)",
)
@click.option("--days", "-d", default=None, type=int, help="Only show speeches from the last N days")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def speeches_list(folder, page_size: int, source: str, days: int, as_json: bool):
    """List all speeches."""
    client = get_authenticated_client()

    # Resolve folder name to ID if needed
    folder_id = folder
    if isinstance(folder, str) and not str(folder).isdigit():
        folder_id = _resolve_folder_id(client, str(folder))
    else:
        folder_id = int(folder) if folder else 0

    try:
        result = client.get_speeches(folder=folder_id, page_size=page_size, source=source)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to get speeches: {result}", err=True)
        sys.exit(1)

    data = result["data"]
    speeches_data = data.get("speeches", [])

    # Filter by days if specified
    if days is not None and speeches_data:
        cutoff = time.time() - (days * 86400)
        speeches_data = [s for s in speeches_data if s.get("created_at", 0) >= cutoff]
        data["speeches"] = speeches_data

    if as_json:
        click.echo(json.dumps(data, indent=2))
        return

    if not speeches_data:
        click.echo("No speeches found.")
        return

    click.echo(f"Found {len(speeches_data)} speeches:\n")
    for speech in speeches_data:
        title = speech.get("title") or "Untitled"
        otid = speech.get("otid", "")
        created = speech.get("created_at", 0)
        duration = speech.get("duration", 0)
        live = speech.get("live_status", "")
        folder_info = speech.get("folder")
        folder_name = folder_info.get("folder_name", "") if isinstance(folder_info, dict) else ""
        speakers = [sp.get("speaker_name", "") for sp in speech.get("speakers", []) if sp.get("speaker_name")]

        # Title line with live indicator
        live_tag = " [LIVE]" if live == "live" else ""
        click.echo(f"  {otid}  {title}{live_tag}")

        # Details line
        parts = []
        if created:
            parts.append(_format_timestamp(created))
        if duration:
            parts.append(_format_duration(duration))
        if folder_name:
            parts.append(f"📁 {folder_name}")
        if speakers:
            parts.append(f"👤 {', '.join(speakers)}")
        if parts:
            click.echo(f"           {' | '.join(parts)}")
        click.echo()


@speeches.command("get")
@click.argument("speech_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def speeches_get(speech_id: str, as_json: bool):
    """Get details of a specific speech."""
    client = get_authenticated_client()

    try:
        result = client.get_speech(speech_id)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to get speech: {result}", err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(result["data"], indent=2))
        return

    data = result["data"]
    speech = data.get("speech", {})
    click.echo(f"Title: {speech.get('title', 'Untitled')}")
    click.echo(f"ID (otid): {speech.get('otid', '')}")
    created = speech.get("created_at", 0)
    click.echo(f"Created: {_format_timestamp(created)} ({created})")
    duration = speech.get("duration", 0)
    click.echo(f"Duration: {_format_duration(duration)} ({duration}s)")
    folder_info = speech.get("folder")
    if isinstance(folder_info, dict) and folder_info.get("folder_name"):
        click.echo(f"Folder: {folder_info['folder_name']} (ID: {folder_info.get('id', '')})")
    speakers = speech.get("speakers", [])
    if speakers:
        names = [s.get("speaker_name", "") for s in speakers if s.get("speaker_name")]
        if names:
            click.echo(f"Speakers: {', '.join(names)}")

    # Print transcript if available (support both nested and top-level formats)
    transcripts = speech.get("transcripts") or data.get("transcripts", [])
    if transcripts:
        click.echo("\nTranscript:")
        click.echo("-" * 40)
        for t in transcripts:
            speaker = t.get("speaker_name", "Unknown")
            text = t.get("transcript", "")
            click.echo(f"[{speaker}]: {text}")


@speeches.command("search")
@click.argument("query")
@click.argument("speech_id")
@click.option("--size", "-n", default=500, help="Max results (default: 500)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def speeches_search(query: str, speech_id: str, size: int, as_json: bool):
    """Search within a speech transcript."""
    client = get_authenticated_client()

    try:
        result = client.query_speech(query, speech_id, size=size)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Search failed: {result}", err=True)
        sys.exit(1)

    data = result["data"]

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        matches = data.get("results") or data.get("matches") or data.get("items")
        if isinstance(matches, list) and matches:
            for idx, match in enumerate(matches, start=1):
                text = match.get("transcript") or match.get("text") or ""
                start = match.get("start_time") or match.get("start") or ""
                end = match.get("end_time") or match.get("end") or ""
                header_parts = [f"[{idx}]"]
                if start or end:
                    header_parts.append(f"{start}-{end}".strip("-"))
                click.echo(" ".join(header_parts))
                if text:
                    click.echo(text)
                click.echo()
        elif isinstance(matches, list):
            click.echo("No results found.")
        else:
            click.echo(json.dumps(data, indent=2))


@speeches.command("rename")
@click.argument("speech_id")
@click.argument("title")
def speeches_rename(speech_id: str, title: str):
    """Rename a speech (set new title)."""
    client = get_authenticated_client()

    try:
        result = client.set_speech_title(speech_id, title)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Rename failed: {result}", err=True)
        sys.exit(1)

    click.echo(f"Renamed speech {speech_id} to: {title}")


@speeches.command("download")
@click.argument("speech_id")
@click.option(
    "--format",
    "-f",
    "fileformat",
    default="txt",
    help="Format(s): txt, pdf, mp3, docx, srt (comma-separated, default: txt)",
)
@click.option("--output", "-o", "name", default=None, help="Output filename (optional)")
def speeches_download(speech_id: str, fileformat: str, name: str):
    """Download a speech in specified format(s)."""
    client = get_authenticated_client()

    try:
        result = client.download_speech(speech_id, name=name, fileformat=fileformat)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Download failed: {result}", err=True)
        sys.exit(1)

    filename = result["data"].get("filename", "")
    click.echo(f"Downloaded: {filename}")


@speeches.command("upload")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--content-type",
    "-t",
    default="audio/mp4",
    help="MIME type (default: audio/mp4)",
)
def speeches_upload(file: str, content_type: str):
    """Upload an audio file for transcription."""
    client = get_authenticated_client()

    click.echo(f"Uploading {file}...")

    try:
        result = client.upload_speech(file, content_type=content_type)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Upload failed: {result}", err=True)
        sys.exit(1)

    click.echo("Upload successful! Transcription is processing.")
    click.echo(json.dumps(result["data"], indent=2))


@speeches.command("trash")
@click.argument("speech_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def speeches_trash(speech_id: str, yes: bool):
    """Move a speech to trash."""
    if not yes:
        click.confirm(f"Move speech {speech_id} to trash?", abort=True)

    client = get_authenticated_client()

    try:
        result = client.move_to_trash_bin(speech_id)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to trash speech: {result}", err=True)
        sys.exit(1)

    click.echo(f"Speech {speech_id} moved to trash.")


@speeches.command("move")
@click.argument("speech_ids", nargs=-1, required=True)
@click.option("--folder", "-f", required=True, help="Destination folder ID or name")
@click.option("--create", is_flag=True, help="Create the folder if it doesn't exist (when using folder name)")
def speeches_move(speech_ids: tuple, folder: str, create: bool):
    """Move speech(es) to a folder.

    The --folder option accepts either a numeric folder ID or a folder name.
    Use --create to auto-create the folder if it doesn't exist.

    Examples:
        otter speeches move <speech_id> --folder <folder_id>
        otter speeches move <id1> <id2> --folder "CoverNode"
        otter speeches move <id1> --folder "New Folder" --create
    """
    client = get_authenticated_client()

    # Resolve folder name to ID
    if folder.isdigit():
        folder_id = folder
    else:
        try:
            folder_id = _resolve_folder_id(client, folder)
        except click.ClickException:
            if create:
                # Create the folder
                try:
                    create_result = client.create_folder(folder)
                except OtterAIException as e:
                    click.echo(f"Error creating folder: {e}", err=True)
                    sys.exit(1)
                if create_result["status"] != 200:
                    click.echo(f"Failed to create folder: {create_result}", err=True)
                    sys.exit(1)
                folder_id = str(create_result["data"].get("folder", {}).get("id", ""))
                click.echo(f"Created folder '{folder}' (ID: {folder_id})")
            else:
                raise

    try:
        result = client.add_folder_speeches(folder_id, list(speech_ids))
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to move speeches: {result}", err=True)
        sys.exit(1)

    if len(speech_ids) == 1:
        click.echo(f"Moved speech {speech_ids[0]} to folder {folder}")
    else:
        click.echo(f"Moved {len(speech_ids)} speeches to folder {folder}")


# =============================================================================
# Speakers Commands
# =============================================================================


@main.group()
def speakers():
    """Manage speakers."""
    pass


@speakers.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def speakers_list(as_json: bool):
    """List all speakers."""
    client = get_authenticated_client()

    try:
        result = client.get_speakers()
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to get speakers: {result}", err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(result["data"], indent=2))
        return

    speakers_data = result["data"].get("speakers", [])
    if not speakers_data:
        click.echo("No speakers found.")
        return

    click.echo(f"Found {len(speakers_data)} speakers:\n")
    for speaker in speakers_data:
        name = speaker.get("speaker_name", "Unknown")
        speaker_id = speaker.get("speaker_id", "")
        click.echo(f"  {speaker_id}  {name}")


@speakers.command("create")
@click.argument("name")
def speakers_create(name: str):
    """Create a new speaker."""
    client = get_authenticated_client()

    try:
        result = client.create_speaker(name)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to create speaker: {result}", err=True)
        sys.exit(1)

    click.echo(f"Speaker '{name}' created.")
    click.echo(json.dumps(result["data"], indent=2))


@speakers.command("tag")
@click.argument("speech_id")
@click.argument("speaker_id")
@click.option("--transcript-uuid", "-t", default=None,
              help="Specific transcript UUID to tag")
@click.option("--all", "-a", "tag_all", is_flag=True,
              help="Tag all segments with this speaker")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def speakers_tag(speech_id: str, speaker_id: str, transcript_uuid: str, tag_all: bool, as_json: bool):
    """Tag a speaker on transcript segment(s).

    If no --transcript-uuid or --all is provided, lists available segments.

    Examples:
        otter speakers tag <speech_id> <speaker_id>
        otter speakers tag <speech_id> <speaker_id> -t <uuid>
        otter speakers tag <speech_id> <speaker_id> --all
    """
    client = get_authenticated_client()

    # Get speaker name from speaker_id
    try:
        speakers_result = client.get_speakers()
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if speakers_result["status"] != 200:
        click.echo(f"Failed to get speakers: {speakers_result}", err=True)
        sys.exit(1)

    speaker_name = None
    for s in speakers_result["data"].get("speakers", []):
        if str(s.get("speaker_id")) == str(speaker_id):
            speaker_name = s.get("speaker_name")
            break

    if not speaker_name:
        click.echo(f"Speaker ID {speaker_id} not found.", err=True)
        sys.exit(1)

    # Get speech to find transcript UUIDs
    try:
        speech_result = client.get_speech(speech_id)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if speech_result["status"] != 200:
        click.echo(f"Failed to get speech: {speech_result}", err=True)
        sys.exit(1)

    transcripts = speech_result["data"].get("speech", {}).get("transcripts", [])

    if not transcript_uuid and not tag_all:
        # List available transcript segments
        if as_json:
            segments = []
            for t in transcripts:
                segments.append({
                    "uuid": t.get("uuid", ""),
                    "speaker_id": t.get("speaker_id"),
                    "speaker_name": t.get("speaker_name", "Untagged"),
                    "text_preview": t.get("transcript", "")[:80]
                })
            click.echo(json.dumps(segments, indent=2))
        else:
            click.echo(f"Available transcript segments in {speech_id}:\n")
            for t in transcripts:
                uuid = t.get("uuid", "")
                current_speaker = t.get("speaker_name", "Untagged")
                text = t.get("transcript", "")[:60]
                click.echo(f"  UUID: {uuid}")
                click.echo(f"  Speaker: {current_speaker}")
                click.echo(f"  Text: {text}...")
                click.echo()
            click.echo("Use -t <uuid> to tag a specific segment, or --all to tag all.")
        return

    # Tag specific segment or all
    segments_to_tag = []
    if transcript_uuid:
        segments_to_tag = [transcript_uuid]
    elif tag_all:
        segments_to_tag = [t.get("uuid") for t in transcripts if t.get("uuid")]

    tagged_count = 0
    for uuid in segments_to_tag:
        try:
            result = client.set_transcript_speaker(
                speech_id=speech_id,
                transcript_uuid=uuid,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                create_speaker=False
            )
            if result["status"] == 200:
                tagged_count += 1
                if not tag_all:
                    click.echo(f"Tagged segment {uuid} as '{speaker_name}'")
            else:
                click.echo(f"Failed to tag {uuid}: {result}", err=True)
        except OtterAIException as e:
            click.echo(f"Error tagging {uuid}: {e}", err=True)

    if tag_all:
        click.echo(f"Tagged {tagged_count}/{len(segments_to_tag)} segments as '{speaker_name}'")


# =============================================================================
# Folders Commands
# =============================================================================


@main.group()
def folders():
    """Manage folders."""
    pass


@folders.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def folders_list(as_json: bool):
    """List all folders."""
    client = get_authenticated_client()

    try:
        result = client.get_folders()
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to get folders: {result}", err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(result["data"], indent=2))
        return

    folders_data = result["data"].get("folders", [])
    if not folders_data:
        click.echo("No folders found.")
        return

    click.echo(f"Found {len(folders_data)} folders:\n")
    for folder in folders_data:
        name = folder.get("folder_name", "Untitled")
        folder_id = folder.get("id", "")
        speech_count = folder.get("speech_count", 0)
        click.echo(f"  {folder_id}  {name} ({speech_count} speeches)")


@folders.command("create")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def folders_create(name: str, as_json: bool):
    """Create a new folder."""
    client = get_authenticated_client()

    try:
        result = client.create_folder(name)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to create folder: {result}", err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps(result["data"], indent=2))
    else:
        folder_data = result["data"].get("folder", {})
        folder_id = folder_data.get("id", "unknown")
        click.echo(f"Created folder '{name}' (ID: {folder_id})")


@folders.command("rename")
@click.argument("folder_id")
@click.argument("new_name")
def folders_rename(folder_id: str, new_name: str):
    """Rename a folder."""
    client = get_authenticated_client()

    try:
        result = client.rename_folder(folder_id, new_name)
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to rename folder: {result}", err=True)
        sys.exit(1)

    click.echo(f"Renamed folder {folder_id} to '{new_name}'")


# =============================================================================
# Groups Commands
# =============================================================================


@main.group()
def groups():
    """Manage groups."""
    pass


@groups.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def groups_list(as_json: bool):
    """List all groups."""
    client = get_authenticated_client()

    try:
        result = client.list_groups()
    except OtterAIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to get groups: {result}", err=True)
        sys.exit(1)

    data = result["data"]

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        if isinstance(data, list):
            if not data:
                click.echo("No groups found.")
            else:
                click.echo(f"Found {len(data)} groups:")
                for idx, group in enumerate(data, start=1):
                    if isinstance(group, dict):
                        name = group.get("name") or group.get("group_name") or "Unknown"
                        group_id = group.get("id")
                        if group_id is not None:
                            click.echo(f"  {idx}. {name} (id: {group_id})")
                        else:
                            click.echo(f"  {idx}. {name}")
                    else:
                        click.echo(f"  {idx}. {group}")
        else:
            click.echo(json.dumps(data, indent=2))


# =============================================================================
# Config Commands
# =============================================================================


@main.group()
def config():
    """Manage CLI configuration."""
    pass


@config.command("show")
def config_show():
    """Show current configuration."""
    username, password = load_credentials()
    config_path = get_config_path()

    click.echo(f"Config file: {config_path}")
    click.echo(f"Config exists: {config_path.exists()}")

    if username:
        click.echo(f"Username: {username}")
        click.echo(f"Password: {'*' * len(password) if password else 'Not set'}")
    else:
        click.echo("Not logged in.")


@config.command("clear")
def config_clear():
    """Clear saved configuration."""
    if clear_credentials():
        click.echo("Configuration cleared.")
    else:
        click.echo("No configuration found.")


if __name__ == "__main__":
    main()
