import click

from ..config import clear_credentials, get_config_path, load_credentials


@click.group("config")
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
