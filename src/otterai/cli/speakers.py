import json
import sys

import click

from ..client import OtterAIError
from .helpers import get_authenticated_client


@click.group()
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
    except OtterAIError as e:
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
    except OtterAIError as e:
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
@click.option(
    "--transcript-uuid", "-t", default=None, help="Specific transcript UUID to tag"
)
@click.option(
    "--all", "-a", "tag_all", is_flag=True, help="Tag all segments with this speaker"
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def speakers_tag(
    speech_id: str,
    speaker_id: str,
    transcript_uuid: str,
    tag_all: bool,
    as_json: bool,
):
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
    except OtterAIError as e:
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
    except OtterAIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if speech_result["status"] != 200:
        click.echo(f"Failed to get speech: {speech_result}", err=True)
        sys.exit(1)

    transcripts = (
        speech_result["data"].get("speech", {}).get("transcripts", [])
    )

    if not transcript_uuid and not tag_all:
        # List available transcript segments
        if as_json:
            segments = []
            for t in transcripts:
                segments.append(
                    {
                        "uuid": t.get("uuid", ""),
                        "speaker_id": t.get("speaker_id"),
                        "speaker_name": t.get("speaker_name", "Untagged"),
                        "text_preview": t.get("transcript", "")[:80],
                    }
                )
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
            click.echo(
                "Use -t <uuid> to tag a specific segment, or --all to tag all."
            )
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
                create_speaker=False,
            )
            if result["status"] == 200:
                tagged_count += 1
                if not tag_all:
                    click.echo(f"Tagged segment {uuid} as '{speaker_name}'")
            else:
                click.echo(f"Failed to tag {uuid}: {result}", err=True)
        except OtterAIError as e:
            click.echo(f"Error tagging {uuid}: {e}", err=True)

    if tag_all:
        click.echo(
            f"Tagged {tagged_count}/{len(segments_to_tag)} segments as '{speaker_name}'"
        )
