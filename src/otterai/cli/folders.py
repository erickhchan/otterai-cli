import json
import sys

import click

from ..client import OtterAIError
from .helpers import get_authenticated_client


@click.group()
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
    except OtterAIError as e:
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
    except OtterAIError as e:
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
    except OtterAIError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if result["status"] != 200:
        click.echo(f"Failed to rename folder: {result}", err=True)
        sys.exit(1)

    click.echo(f"Renamed folder {folder_id} to '{new_name}'")
