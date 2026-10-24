"""Command line: `cricket modules | run | schema | resolve | setup | ingest`.

    cricket modules
    cricket run batting --player "V Kohli" --competition ipl --group_by season --json
    cricket schema --json
    cricket resolve kohli
    cricket ingest --db data/new.duckdb --no-download
"""

import json
import logging
from pathlib import Path

import click


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def cli(verbose: bool):
    """Cricket Analytics Platform."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(levelname)s | %(message)s")


@cli.command()
def setup():
    """Initialise the database schema and normalise existing venue names."""
    from .db import init_schema
    from .ingest.venues import migrate_venues
    init_schema()
    click.echo("Database schema initialised.")
    n = migrate_venues()
    if n:
        click.echo(f"Normalised {n} venue name(s) in DB.")


@cli.command()
@click.option("--format", "fmt", default=None, help="Cricsheet key: t20s, ipl, bbl, psl, cpl, sa20, hundred, blast")
@click.option("--redownload", is_flag=True, default=False, help="Force re-download even if data exists")
@click.option("--no-download", "skip_download", is_flag=True, default=False, help="Skip download, load existing files only")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="Output DuckDB file (default data/cricket_analytics.duckdb; the slim DB is refused)")
def ingest(fmt, redownload, skip_download, db_path):
    """Ingest Cricsheet data into DuckDB."""
    from .ingest.cricsheet import ingest as run_ingest, default_db_path, get_path
    db_path = db_path or default_db_path()
    click.echo(f"Writing to {db_path}")
    if redownload and fmt:
        import shutil
        raw_dir = get_path("raw") / "cricsheet" / fmt
        if raw_dir.exists():
            shutil.rmtree(raw_dir)
            click.echo(f"Cleared {raw_dir}")
    results = run_ingest(formats=[fmt] if fmt else None, download=not skip_download, db_path=db_path)
    for f, count in results.items():
        click.echo(f"{f}: {count:,} deliveries loaded")


@cli.command("modules")
def modules_cmd():
    """List analysis modules."""
    from . import api
    click.echo(f"{'ID':<12} {'Category':<13} {'Title':<28} Params")
    for m in api.list_modules():
        click.echo(f"{m['id']:<12} {m['category']:<13} {m['title']:<28} {', '.join(m['params'])}")


def _parse_extra(args: list[str]) -> dict:
    """['--player', 'V Kohli', '--min_balls=50', '--include_super_overs'] -> strings; api.run converts them by type"""
    out, i = {}, 0
    while i < len(args):
        a = args[i]
        if not a.startswith("--"):
            raise click.UsageError(f"Unexpected argument {a!r}; params look like --name value")
        key, eq, val = a[2:].partition("=")
        if not eq:
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                i += 1
                val = args[i]
            else:
                val = "true"   # bare flag such as --include_super_overs; non-bool params reject it with a clear message
        out[key.replace("-", "_")] = val
        i += 1
    return out


@cli.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("module_id")
@click.option("--json", "as_json", is_flag=True, help='Print {"meta": ..., "data": [...]}')
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), help="Write output to a file (.json, else CSV)")
@click.option("--limit", default=20, show_default=True, help="Rows to show in table mode")
@click.pass_context
def run(ctx, module_id, as_json, out, limit):
    """Run a module. Any module param works as --name value (see `cricket schema`)."""
    from . import api
    try:
        r = api.run(module_id, **_parse_extra(ctx.args))
    except ValueError as e:
        raise click.ClickException(str(e))
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        if as_json or out.suffix == ".json":
            out.write_text(r.to_json(indent=2), encoding="utf-8")
        else:
            r.data.to_csv(out, index=False)
        click.echo(f"Wrote {len(r.data)} rows to {out}")
    elif as_json:
        click.echo(r.to_json())
    else:
        m = r.meta
        click.echo(f"{m['title']} | data through {m['data_through']} | {m['row_count']} rows | params {m['params']}")
        click.echo(r.data.head(limit).to_string(index=False) if len(r.data) else "No rows for these filters.")
        for c in m["caveats"]:
            click.echo(f"note: {c}")


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON Schema tool definitions for every module")
def schema(as_json):
    """Describe module params (JSON Schema with --json, usable as LLM tool definitions)."""
    from . import api, registry
    if as_json:
        click.echo(json.dumps(api.schema(), indent=2))
        return
    for m in registry.all_modules():
        click.echo(f"{m.id}: {m.title}\n  {m.description}")
        for p in m.params:
            extra = f" choices={list(p.choices)}" if p.choices else ""
            dflt = f" default={p.default}" if p.default is not None else ""
            click.echo(f"  --{p.name:<12} {p.kind}{extra}{dflt}{'  (required)' if p.required else ''}")


@cli.command()
@click.argument("name")
@click.option("--competition", default=None, help="Limit to one competition key")
@click.option("--team", "is_team", is_flag=True, help="Look up a team name instead of a player")
@click.option("--limit", default=5, show_default=True)
def resolve(name, competition, is_team, limit):
    """Find the exact data name for a loose spelling: cricket resolve kohli."""
    from . import api
    try:
        rows = (api.resolve_team if is_team else api.resolve_player)(name, competition, limit)
    except ValueError as e:
        raise click.ClickException(str(e))
    for r in rows:
        extra = "" if is_team else f"  {r['matches']:>4} matches, last {r['last_match']}"
        click.echo(f"{r['score']:.3f}  {r['name']}{extra}")


@cli.command("info")
def info_cmd():
    """Show what is in the database (matches and latest date per competition)."""
    from . import api
    d = api.data_info()
    click.echo(f"{d['db_path']} (modified {d['db_modified']})")
    for c in d["competitions"]:
        click.echo(f"{c['competition']:<11} {c['matches']:>6} matches  {c['earliest']} .. {c['latest']}")


if __name__ == "__main__":
    cli()
