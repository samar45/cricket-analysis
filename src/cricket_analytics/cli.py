"""CLI entry point — run modules, ingest data, manage the platform.

Usage:
    cricket setup              # Init database
    cricket ingest             # Download & load all Cricsheet data
    cricket ingest --format ipl  # Download & load IPL only
    cricket modules            # List available modules
    cricket run B1             # Run batting stats
    cricket run B1 --player "Kohli" --format T20
"""

import logging
import sys

import click


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def cli(verbose: bool):
    """Cricket Analytics Platform."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s | %(message)s")


@cli.command()
def setup():
    """Initialise the database schema."""
    from src.cricket_analytics.db import init_schema
    init_schema()
    click.echo("Database schema initialised.")


@cli.command()
@click.option("--format", "fmt", default=None, help="Format: ipl, t20s, odis, tests")
@click.option("--redownload", is_flag=True, default=False, help="Force re-download even if data exists")
@click.option("--no-download", "skip_download", is_flag=True, default=False, help="Skip download, load existing files only")
def ingest(fmt: str | None, redownload: bool, skip_download: bool):
    """Ingest Cricsheet data into DuckDB."""
    from ingestion.cricsheet import ingest as run_ingest, download_cricsheet, get_path
    formats = [fmt] if fmt else None

    if redownload and fmt:
        import shutil
        raw_dir = get_path("raw") / "cricsheet" / fmt
        if raw_dir.exists():
            shutil.rmtree(raw_dir)
            click.echo(f"Cleared {raw_dir}")

    results = run_ingest(formats=formats, download=not skip_download)
    for f, count in results.items():
        click.echo(f"{f}: {count:,} deliveries loaded")


@cli.command("modules")
def list_modules_cmd():
    """List all registered analysis modules."""
    import modules.basic  # noqa: F401 — triggers registration
    from modules.base import list_modules
    mods = list_modules()
    if not mods:
        click.echo("No modules registered.")
        return
    click.echo(f"{'ID':<6} {'Category':<14} Name")
    click.echo("-" * 50)
    for m in mods:
        click.echo(f"{m['id']:<6} {m['category']:<14} {m['name']}")


@cli.command()
@click.argument("module_id")
@click.option("--player", default=None)
@click.option("--team", default=None)
@click.option("--season", default=None, type=int)
@click.option("--format", "fmt", default="T20")
@click.option("--venue", default=None)
@click.option("--opposition", default=None)
@click.option("--phase", default=None, type=click.Choice(["powerplay", "middle", "death"]))
@click.option("--output", "out", default="dataframe", type=click.Choice(["dataframe", "plot"]))
@click.option("--limit", default=20, help="Max rows to display")
def run(module_id, player, team, season, fmt, venue, opposition, phase, out, limit):
    """Run an analysis module. Example: cricket run B1 --player Kohli"""
    import modules.basic  # noqa: F401
    from modules.base import get_module, ModuleParams

    params = ModuleParams(
        player=player, team=team, season=season, format=fmt,
        venue=venue, opposition=opposition, phase=phase, output=out,
    )

    module = get_module(module_id)
    click.echo(f"Running [{module.module_id}] {module.module_name}...\n")

    result = module.execute(params)

    if out == "plot":
        if result:
            result.show()
        else:
            click.echo("No data to plot.")
    else:
        if result.empty:
            click.echo("No results found for the given filters.")
        else:
            click.echo(result.head(limit).to_string(index=False))
            if len(result) > limit:
                click.echo(f"\n... showing {limit} of {len(result)} rows")


if __name__ == "__main__":
    cli()
