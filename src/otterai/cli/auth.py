import json
import sys

import click

from ..client import OtterAIClient
from ..config import clear_credentials, get_config_path, save_credentials
from .helpers import get_authenticated_client


def register(main: click.Group):
    main.add_command(login)
    main.add_command(logout)
    main.add_command(user)


@click.command()
@click.option("--username", "-u", prompt=True, help="Otter.ai username (email)")
@click.option(
    "--password", "-p", prompt=True, hide_input=True, help="Otter.ai password"
)
def login(username: str, password: str):
    """Authenticate with Otter.ai and save credentials."""
    client = OtterAIClient()
    result = client.login(username, password)

    if result["status"] != 200:
        click.echo(f"Login failed: {result.get('data', {})}", err=True)
        sys.exit(1)

    backend = save_credentials(username, password)
    user_data = result.get("data", {})
    click.echo(f"Logged in as {user_data.get('email', username)}")
    if backend == "keyring":
        click.echo("Credentials saved to system keyring")
    else:
        click.echo(f"Credentials saved to {get_config_path()}")


@click.command()
def logout():
    """Clear saved credentials."""
    if clear_credentials():
        click.echo("Credentials cleared.")
    else:
        click.echo("No saved credentials found.")


@click.command()
def user():
    """Show current user information."""
    client = get_authenticated_client()
    result = client.get_user()

    if result["status"] != 200:
        click.echo(f"Failed to get user: {result}", err=True)
        sys.exit(1)

    click.echo(json.dumps(result["data"], indent=2))
