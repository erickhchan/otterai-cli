import json
import sys

import click

from ..client import OtterAIError
from .helpers import get_authenticated_client


@click.group()
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
    except OtterAIError as e:
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
                        name = (
                            group.get("name")
                            or group.get("group_name")
                            or "Unknown"
                        )
                        group_id = group.get("id")
                        if group_id is not None:
                            click.echo(f"  {idx}. {name} (id: {group_id})")
                        else:
                            click.echo(f"  {idx}. {name}")
                    else:
                        click.echo(f"  {idx}. {group}")
        else:
            click.echo(json.dumps(data, indent=2))
