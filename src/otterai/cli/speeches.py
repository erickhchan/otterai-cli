import json
import sys
import time

import click

from ..client import OtterAIError
from .helpers import (
    get_authenticated_client,
    _format_timestamp,
    _format_duration,
    _resolve_folder_id,
    FRONTMATTER_AVAILABLE_FIELDS,
    parse_frontmatter_fields,
    format_speech_markdown,
    _speaker_names_by_id,
    _resolve_transcript_speaker,
)


@click.group()
def speeches():
    """Manage speeches (transcripts)."""
    pass


@speeches.command("list")
@click.option(
    "--folder",
    "-f",
    default="0",
    type=str,
    help="Folder ID or name (default: 0 = all)",
)
@click.option("--page-size", "-n", default=45, help="Number of results (default: 45)")
@click.option(
    "--source",
    "-s",
    default="owned",
    type=click.Choice(["owned", "shared", "all"]),
    help="Source filter (default: owned)",
)
@click.option(
    "--days",
    "-d",
    default=None,
    type=int,
    help="Only show speeches from the last N days",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def speeches_list(folder: str, page_size: int, source: str, days: int, as_json: bool):
    """List all speeches."""
    client = get_authenticated_client()

    # Resolve folder name to ID if needed
    folder_ref = str(folder).strip()
    if folder_ref and not folder_ref.isdigit():
        folder_id = _resolve_folder_id(client, folder_ref)
    else:
        folder_id = int(folder_ref) if folder_ref else 0

    try:
        result = client.get_speeches(
            folder=folder_id, page_size=page_size, source=source
        )
    except OtterAIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to get speeches: {result}", err=True)
        sys.exit(1)

    data = result["data"]
    speeches_data = data.get("speeches", [])

    # Otter's API can return cross-folder items even when folder is specified.
    # Apply client-side filtering when folder metadata is present.
    if folder_id != 0 and speeches_data:
        target_folder_id = str(folder_id)
        target_folder_name = folder_ref.lower() if not folder_ref.isdigit() else None

        def _matches_requested_folder(speech: dict) -> bool:
            folder_info = speech.get("folder")
            if not isinstance(folder_info, dict):
                return False
            if str(folder_info.get("id", "")) == target_folder_id:
                return True
            if target_folder_name and folder_info.get(
                "folder_name", ""
            ).lower() == target_folder_name:
                return True
            return False

        if any(isinstance(s.get("folder"), dict) for s in speeches_data):
            speeches_data = [s for s in speeches_data if _matches_requested_folder(s)]
            data["speeches"] = speeches_data

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
        folder_name = (
            folder_info.get("folder_name", "") if isinstance(folder_info, dict) else ""
        )
        speakers = [
            sp.get("speaker_name", "")
            for sp in speech.get("speakers", [])
            if sp.get("speaker_name")
        ]

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
    except OtterAIError as e:
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
        click.echo(
            f"Folder: {folder_info['folder_name']} (ID: {folder_info.get('id', '')})"
        )
    speakers = speech.get("speakers", [])
    if speakers:
        names = [
            s.get("speaker_name", "") for s in speakers if s.get("speaker_name")
        ]
        if names:
            click.echo(f"Speakers: {', '.join(names)}")

    # Print transcript if available (support both nested and top-level formats)
    transcripts = speech.get("transcripts") or data.get("transcripts", [])
    if transcripts:
        speaker_names = _speaker_names_by_id(speech)
        click.echo("\nTranscript:")
        click.echo("-" * 40)
        for t in transcripts:
            speaker = _resolve_transcript_speaker(t, speaker_names)
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
    except OtterAIError as e:
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
    except OtterAIError as e:
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
    help="Format(s): txt, pdf, mp3, docx, srt, md (comma-separated, default: txt)",
)
@click.option(
    "--output", "-o", "name", default=None, help="Output filename (optional)"
)
@click.option(
    "--frontmatter-fields",
    default="default",
    help=(
        "For md only: comma-separated frontmatter fields, or 'default'/'none'. "
        f"Available: {', '.join(FRONTMATTER_AVAILABLE_FIELDS)}"
    ),
)
def speeches_download(
    speech_id: str,
    fileformat: str,
    name: str,
    frontmatter_fields: str,
):
    """Download a speech in specified format(s)."""
    client = get_authenticated_client()
    frontmatter_fields_spec = (frontmatter_fields or "").strip().lower()

    # Handle markdown format locally (not supported by bulk_export API)
    formats = [f.strip() for f in fileformat.split(",")]
    has_md = any(f in ("md", "markdown") for f in formats)
    if has_md and len(formats) > 1:
        click.echo(
            "Error: md format cannot be combined with other formats.", err=True
        )
        sys.exit(1)
    if not has_md and (frontmatter_fields_spec not in ("", "default")):
        click.echo(
            "Error: --frontmatter-fields is only valid with md format.",
            err=True,
        )
        sys.exit(1)
    if has_md:
        try:
            selected_fields = parse_frontmatter_fields(frontmatter_fields)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        try:
            result = client.get_speech(speech_id)
        except OtterAIError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        if result["status"] != 200:
            click.echo(f"Failed to get speech: {result}", err=True)
            sys.exit(1)

        content = format_speech_markdown(
            result["data"],
            frontmatter_fields=selected_fields,
        )
        filename = (name if name is not None else speech_id) + ".md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(f"Downloaded: {filename}")
        return

    try:
        result = client.download_speech(speech_id, name=name, fileformat=fileformat)
    except OtterAIError as e:
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
    except OtterAIError as e:
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
    except OtterAIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to trash speech: {result}", err=True)
        sys.exit(1)

    click.echo(f"Speech {speech_id} moved to trash.")


@speeches.command("move")
@click.argument("speech_ids", nargs=-1, required=True)
@click.option(
    "--folder", "-f", required=True, help="Destination folder ID or name"
)
@click.option(
    "--create",
    is_flag=True,
    help="Create the folder if it doesn't exist (when using folder name)",
)
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
                except OtterAIError as e:
                    click.echo(f"Error creating folder: {e}", err=True)
                    sys.exit(1)
                if create_result["status"] != 200:
                    click.echo(
                        f"Failed to create folder: {create_result}", err=True
                    )
                    sys.exit(1)
                folder_id = str(
                    create_result["data"].get("folder", {}).get("id", "")
                )
                click.echo(f"Created folder '{folder}' (ID: {folder_id})")
            else:
                raise

    try:
        result = client.add_folder_speeches(folder_id, list(speech_ids))
    except OtterAIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to move speeches: {result}", err=True)
        sys.exit(1)

    if len(speech_ids) == 1:
        click.echo(f"Moved speech {speech_ids[0]} to folder {folder}")
    else:
        click.echo(f"Moved {len(speech_ids)} speeches to folder {folder}")
