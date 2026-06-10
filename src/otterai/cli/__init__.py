import click

from . import auth
from .speeches import speeches
from .speakers import speakers
from .folders import folders
from .groups import groups
from .config_cmd import config


@click.group()
@click.version_option(version="0.1.4", prog_name="otter")
def main():
    """OtterAI CLI - Interact with Otter.ai from the command line."""
    pass


# Register top-level commands (login, logout, user)
auth.register(main)

# Register subcommand groups
main.add_command(speeches)
main.add_command(speakers)
main.add_command(folders)
main.add_command(groups)
main.add_command(config)
