"""CLI glue for SMAT scouting (hooked from cli.py): resolve/facts/chart --scouting smat2025, and `cricket scouting list`."""
import json
from pathlib import Path

import click

from . import reels


def _fail(e: "reels.NotExact"):
    lines = [f"  {c['name']}  ({c['team']}, cricbuzz_id {c['cricbuzz_id']}, {c['role']})" for c in e.candidates]
    raise click.ClickException(f"{e}. Candidates:\n" + ("\n".join(lines) or "  (none)"))


def _check(scouting):
    if scouting != "smat2025":
        raise click.ClickException(f"unknown scouting set {scouting!r}; only smat2025")


def do_resolve(scouting, name):
    _check(scouting)
    try:
        c = reels.resolve(name)
    except reels.NotExact as e:
        _fail(e)
    click.echo(f"{c['cricbuzz_id']}  {c['name']}  {c['team']}  ({c['role']})")


def do_facts(scouting, player, out, role=None):
    _check(scouting)
    try:
        data = reels.build_facts(player, role)
    except reels.NotExact as e:
        _fail(e)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    click.echo(f"Wrote {out}: {len(data['tokens'])} tokens, data through {data['meta']['data_through']}")


def do_chart(scouting, chart, png, size, palette, extra: dict):
    import logging

    from . import charts
    _check(scouting)
    if not png:
        raise click.UsageError("Give --png")
    logging.getLogger().setLevel(logging.WARNING)
    try:
        charts.render(chart, png, size, palette, **extra)
    except reels.NotExact as e:
        _fail(e)
    except (ValueError, KeyError) as e:
        raise click.ClickException(str(e))
    click.echo(f"Wrote {png}")


@click.group("scouting")
def scouting_group():
    """Domestic scouting tables for reels."""


@scouting_group.command("list")
@click.argument("name")
@click.option("--role", type=click.Choice(["bat", "bowl"]), required=True)
@click.option("--uncapped", is_flag=True, help="No men's T20I in the DB")
@click.option("--no-ipl", is_flag=True, help="ipl_status = 'no IPL record'")
@click.option("--top", default=15, show_default=True)
@click.option("--json", "as_json", is_flag=True)
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), default=None)
def list_cmd(name, role, uncapped, no_ipl, top, as_json, out):
    """cricket scouting list smat2025 --uncapped --no-ipl --role bat --json"""
    _check(name)
    d = reels.listing(role, uncapped, no_ipl, top)
    text = json.dumps(d, indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    if as_json:
        click.echo(text)
    else:
        for r in d["data"]:
            click.echo(f"{r['rank_uncapped'] or '-':>3}  {r['name']:<22}{r['team']:<16}{r['score']:>7}  {r['ipl_status']}")
