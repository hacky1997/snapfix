from __future__ import annotations

import pathlib

import typer

from snapfix.config import SnapfixConfig
from snapfix.store import SnapfixStore

app = typer.Typer(
    name="snapfix",
    help="Capture real Python objects, scrub PII, emit pytest fixtures.",
    no_args_is_help=True,
    add_completion=False,
)


def _store(output_dir: pathlib.Path | None = None) -> SnapfixStore:
    cfg = SnapfixConfig.from_env()
    return SnapfixStore(output_dir or cfg.output_dir)


@app.command("list")
def list_fixtures(
    output_dir: pathlib.Path | None = typer.Option(
        None, "--dir", "-d", help="Fixture output directory (default: from config)."
    ),
) -> None:
    """List all captured fixtures."""
    store   = _store(output_dir)
    entries = store.list()
    if not entries:
        typer.echo("No fixtures captured yet.")
        raise typer.Exit(0)
    for e in entries:
        path     = e.get("path", "?")
        scrubbed = e.get("scrubbed_fields", [])
        captured = e.get("captured_at", "")
        typer.echo(f"  {path}")
        if captured:
            typer.echo(f"    captured : {captured}")
        if scrubbed:
            typer.echo(f"    scrubbed : {', '.join(scrubbed)}")


@app.command("show")
def show_fixture(
    name: str = typer.Argument(..., help="Fixture name (without snapfix_ prefix)."),
    output_dir: pathlib.Path | None = typer.Option(None, "--dir", "-d"),
) -> None:
    """Print a captured fixture to stdout."""
    store = _store(output_dir)
    idx   = store._load_index()
    if name not in idx:
        typer.echo(f"No fixture named '{name}'.", err=True)
        raise typer.Exit(1)
    p = pathlib.Path(idx[name]["path"])
    if not p.exists():
        typer.echo(f"File missing: {p}", err=True)
        raise typer.Exit(1)
    typer.echo(p.read_text())


@app.command("clear")
def clear_fixture(
    name: str = typer.Argument(..., help="Fixture name to delete."),
    output_dir: pathlib.Path | None = typer.Option(None, "--dir", "-d"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete a captured fixture."""
    store = _store(output_dir)
    if not store.exists(name):
        typer.echo(f"No fixture named '{name}'.", err=True)
        raise typer.Exit(1)
    if not yes:
        typer.confirm(f"Delete fixture '{name}'?", abort=True)
    deleted = store.delete(name)
    typer.echo(f"Deleted '{name}': {deleted}")


@app.command("clear-all")
def clear_all(
    output_dir: pathlib.Path | None = typer.Option(None, "--dir", "-d"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete all captured fixtures."""
    store   = _store(output_dir)
    entries = store.list()
    if not entries:
        typer.echo("Nothing to clear.")
        raise typer.Exit(0)
    if not yes:
        typer.confirm(f"Delete all {len(entries)} fixture(s)?", abort=True)
    for e in entries:
        name = pathlib.Path(e["path"]).stem.removeprefix("snapfix_")
        store.delete(name)
    typer.echo(f"Cleared {len(entries)} fixture(s).")
