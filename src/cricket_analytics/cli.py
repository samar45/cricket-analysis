"""Command line: `cricket modules | run | schema | resolve | ask | facts | chart | update | health | runs | setup | ingest`.

    cricket modules
    cricket run batting --player "V Kohli" --competition ipl --group_by season --json
    cricket run batting --player "V Kohli" --competition ipl --last_n_years 5
    cricket run batting --player "V Kohli" --venue "Wankhede Stadium" --venue "Eden Gardens"
    cricket schema --json
    cricket resolve kohli
    cricket ingest --db data/new.duckdb --no-download
"""

import json
import logging
import sys
from pathlib import Path

import click


class _LoggedGroup(click.Group):
    """Any unexpected exception in a command goes to logs/errors.log; the user sees the message plus an error id."""

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except (click.ClickException, click.exceptions.Exit, click.Abort):
            raise
        except Exception as e:
            from .applog import log_error
            eid = log_error(f"cli:{ctx.invoked_subcommand}", e, argv=sys.argv[1:])
            raise click.ClickException(f"{type(e).__name__}: {e} (error id {eid})") from e


@click.group(cls=_LoggedGroup)
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
    """['--player', 'V Kohli', '--min_balls=50', '--include_super_overs'] -> strings; api.run converts them by type.
    A flag given twice or more becomes a list: --venue A --venue B -> {'venue': ['A', 'B']}."""
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
        key = key.replace("-", "_")
        if key in out:
            out[key] = [*out[key], val] if isinstance(out[key], list) else [out[key], val]
        else:
            out[key] = val
        i += 1
    return out


def _split_commas(module_id: str, given: dict) -> dict:
    """--team "A, B" -> ['A', 'B'] for multi params, except venues: their names contain commas (repeat --venue)."""
    from . import registry
    mod = registry.get(module_id)
    for key, val in given.items():
        spec = mod.spec(key)
        if spec and spec.multi and spec.kind != "venue":
            vals = val if isinstance(val, list) else [val]
            given[key] = [x.strip() for v in vals for x in v.split(",") if x.strip()]
    return given


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
        r = api.run(module_id, **_split_commas(module_id, _parse_extra(ctx.args)))
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
            extra = (f" choices={list(p.choices)}" if p.choices else "") + (" (repeatable)" if p.multi else "")
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


@cli.command()
@click.option("--player", required=True, help="Exact Cricsheet name, e.g. 'V Kohli' (find it with `cricket resolve`)")
@click.option("--competition", default=None, help="Competition key; omit for all men's T20")
@click.option("--last_n_years", type=int, default=None, help="Only the N most recent seasons")
@click.option("--out", type=click.Path(dir_okay=False, path_type=Path), required=True, help="Write the facts JSON here")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=None, help="DB file (default: the main DB)")
def facts(player, competition, last_n_years, out, db_path):
    """One JSON of headline facts for a reel: career, best season, phases, pace/spin, home/away, pressure, tokens."""
    from . import facts as F
    try:
        data = F.build(player, competition, last_n_years, db_path=db_path)
    except F.PlayerNotFound as e:
        lines = [f"  {c['score']:.3f}  {c['name']}  {c['matches']} matches, last {c['last_match']}" for c in e.candidates]
        raise click.ClickException(f"{e}. Closest names:\n" + ("\n".join(lines) or "  (none)"))
    except ValueError as e:
        raise click.ClickException(str(e))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    m = data["meta"]
    click.echo(f"Wrote {out}: {len(data['facts'])} sections, {len(data['tokens'])} tokens, data through {m['data_through']}")
    if m["competition_note"]:
        click.echo(f"note: {m['competition_note']}")
    for sk in m["skipped"]:
        click.echo(f"skipped {sk['section']}: {sk['reason']}")


@cli.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("module_id")
@click.option("--aspect", type=click.Choice(["9:16", "1:1"]), default="9:16", show_default=True)
@click.option("--focus", default=None, help="Sub-view of the chart (a metric, player or phase; see viz/video/<module>.py)")
@click.option("--png", type=click.Path(dir_okay=False, path_type=Path), help="Write a PNG (1080 px wide)")
@click.option("--html", type=click.Path(dir_okay=False, path_type=Path), help="Write a standalone interactive HTML")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=None)
@click.pass_context
def chart(ctx, module_id, aspect, focus, png, html, db_path):
    """Reel-ready chart: cricket chart batting --player "V Kohli" --competition ipl --aspect 9:16 --png card.png."""
    from . import export
    logging.getLogger().setLevel(logging.WARNING)   # kaleido logs every browser step at INFO
    if not (png or html):
        raise click.UsageError("Give --png and/or --html")
    try:
        _, r = export.render(module_id, aspect, focus, png, html, db_path=db_path,
                             **_split_commas(module_id, _parse_extra(ctx.args)))
    except ValueError as e:   # bad params, unknown module, empty result
        raise click.ClickException(str(e))
    except Exception as e:    # kaleido / browser problems
        raise click.ClickException(f"Could not write the image ({type(e).__name__}: {e}). PNG needs kaleido and Edge/Chrome.")
    for p in (png, html):
        if p:
            click.echo(f"Wrote {p} ({r.meta['row_count']} rows, data through {r.meta['data_through']})")


@cli.command()
@click.option("--days", type=click.Choice(["7", "30"]), default="30", show_default=True, help="Cricsheet recently-added window")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=None, help="DB to update (default: the main DB)")
@click.option("--dry-run", is_flag=True, help="Only classify and count; change nothing")
@click.option("--no-download", "no_download", is_flag=True, help="Use zips already in today's updates folder")
@click.option("--replace-changed", is_flag=True, help="Also reload matches whose numbers changed at Cricsheet")
def update(days, db_path, dry_run, no_download, replace_changed):
    """Add recently-added Cricsheet matches to the DB (old DB kept as _prev_<date>)."""
    try:
        from .ingest.update import run_update   # lazy: another module, imported only when used
    except ImportError:
        raise click.ClickException("ingest/update.py has no run_update yet.")
    try:
        report = run_update(db_path, days=int(days), include_female=True, dry_run=dry_run, download=not no_download,
                            replace_changed=replace_changed)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        raise click.ClickException(str(e))
    click.echo(f"Run log: {report['log_path']}")   # the summary was printed by run_update
    if report.get("ok") is False:
        raise click.ClickException("Checks failed; the DB was not swapped. See the log above.")


@cli.command()
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=None, help="DB to audit (default: the main DB)")
def health(db_path):
    """Read-only audit of the DB: counts, integrity, golden numbers. Logged to data/runs/."""
    from .ingest.update import run_health
    try:
        r = run_health(db_path)
    except Exception as e:
        raise click.ClickException(str(e))
    if not r["ok"]:
        raise click.ClickException(f"Health check failed: {r['failed']}")


@cli.command()
@click.option("--last", default=10, show_default=True, help="How many runs to list")
@click.option("--db", "db_path", type=click.Path(dir_okay=False, path_type=Path), default=None, help="DB whose data/runs folder to read")
def runs(last, db_path):
    """List logged update / health runs, newest first."""
    from .ingest.cricsheet import default_db_path
    from .runlog import list_runs
    for r in list_runs(db_path or default_db_path(), last):
        bad = sum(c["status"] == "fail" for c in r["checks"]) + sum(g["status"] == "fail" for g in r["golden"])
        click.echo(f"{r['run_id']}  {r['kind']:8}  {'ok  ' if r['ok'] else 'FAIL'}  swapped={r['swapped']}  "
                   f"failed checks={bad}  {r['error'] or ''}")


@cli.command()
@click.argument("question")
@click.option("--model", default=None, help="Ollama model (default: nemotron-3.5-bolt:e4b-q4_K_M)")
@click.option("--json", "as_json", is_flag=True, help="Print the full result as JSON")
def ask(question, model, as_json):
    """Ask in plain English (local Ollama model picks the module; numbers come from the data)."""
    from . import ask as A
    try:
        out = A.ask(question, model or A.DEFAULT_MODEL)
    except A.AskError as e:
        raise click.ClickException(str(e))
    if as_json:
        click.echo(json.dumps(out, indent=2, default=str))
        return
    tc = out["tool_call"]
    click.echo(f"Module: {tc['name'] if tc else '-'}  params: {out['resolved_params']}  ({out['timings']['total_s']} s)")
    for n in out["notes"]:
        click.echo(f"note: {n}")
    click.echo(out["answer"])
    if out["result"]:
        import pandas as pd
        click.echo(pd.DataFrame(out["result"]["rows"]).head(10).to_string(index=False))


@cli.command("ask-log")
@click.option("--last", default=10, show_default=True, help="How many asks to show")
@click.option("--bad", is_flag=True, help="Only thumbs-down, errors and no-tool asks")
@click.option("--to-eval", "to_eval", type=click.Path(dir_okay=False, path_type=Path), default=None,
              help="Write draft eval lines (thumbs-down asks with an expected module) to this file")
def ask_log(last, bad, to_eval):
    """Show recent asks from logs/ask.jsonl, or turn thumbs-down items into draft evals/nlq_questions.jsonl lines."""
    from .applog import read_asks
    if to_eval:
        rows = [a for a in read_asks(bad_only=True) if a["rating"] == "down" and a["expected_module"]]
        to_eval.write_text("".join(json.dumps({
            "id": f"draft{i:02d}", "question": a["question"], "expected_module": a["expected_module"],
            "expected_params": a.get("resolved_params") or {}, "golden": None, "expect_clarification": False}) + "\n"
            for i, a in enumerate(rows, 1)),
                           encoding="utf-8")
        click.echo(f"Wrote {len(rows)} draft line(s) to {to_eval}. expected_params are the model's guess and golden is empty: fix both, then review before adding to the eval set.")
        return
    for a in read_asks(last, bad):
        mod = (a.get("tool_call") or {}).get("name") or "-"
        click.echo(f"{a['ts']}  {a['status']:8} {mod:14} {a['rating'] or '-':5} {a['question']}"
                   + (f"  [{a['comment']}]" if a["comment"] else "") + (f"  ({a['error_id']})" if a.get("error_id") else ""))


if __name__ == "__main__":
    cli()
