"""Main file for nessclient CLI."""

import logging
from importlib import metadata

import click

from .events import events
from .send_command import send_command
from .server import server

LOG_LEVELS = ["error", "warning", "info", "debug"]

_LOGGER = logging.getLogger(__name__)


@click.group()
@click.option("--log-level", type=click.Choice(LOG_LEVELS), default="warning")
def cli(log_level: str) -> None:
    """Create the click CLI group with specified log level."""
    level = getattr(logging, log_level.upper())
    logging.getLogger().setLevel(level)
    _LOGGER.debug("nessclient version: %s", get_version())


@cli.command()
def version() -> None:
    """CLI command to print installed package version."""
    print(get_version())  # noqa: T201 # Valid CLI print


def get_version() -> str:
    """Get the version of the nessclient module."""
    return metadata.version("nessclient")


# Add more commands to the CLI
cli.add_command(events)
cli.add_command(send_command)
cli.add_command(server)

if __name__ == "__main__":
    cli()
