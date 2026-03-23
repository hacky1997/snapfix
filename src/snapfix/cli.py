from __future__ import annotations

import json
import pathlib
import sys
from typing import Optional

import typer

from snapfix.config import SnapfixConfig
from snapfix.store import SnapfixStore
from snapfix.audit import scan_directory, format_report as format_audit_report
from snapfix.verify import verify_directory, format_verify_report

app = typer.Typer(
    name="snapfix",
    help="Capture real Python objects, scrub PII, emit pytest fixtures.",
    no_args_is_help=True,
    add_completion=False,
)


def _store(output_dir: Optional[pathlib.Path] = None) -> SnapfixStore:
    cfg = SnapfixConfig.from_env()
    return SnapfixStore(output_dir or cfg.output_dir)


def _c(text: str, code: str) -> str:
    if sys.stdout.isatty():
        return f"\033[{code}m{text}\033[0m"
    return text


def _default_dir() -> pathlib.Path:
    return SnapfixConfig.from_env().output_dir


# ── list ──────────────────────────────────────────────────────────────────────

@app.command("list")
def list_fixtures(
    output_dir: Optional[pathlib.Path] = typer.Option(
        None, "--dir", "-d", help="Fixture directory (default: from config)."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List all captured fixtures with metadata."""
    store   = _store(output_dir)
    entries = store.list()
    if not entries:
        typer.echo("No fixtures captured yet.")
        raise typer.Exit(0)
    if json_output:
        typer.echo(json.dumps(entries, indent=2, default=str))
        return
    for e in entries:
        path     = e.get("path", "?")
        scrubbed = e.get("scrubbed_fields", [])
        captured = e.get("captured_at", "")
        has_snap = e.get("has_snapshot", False)
        icon     = _c("◉", "32") if has_snap else _c("○", "2")
        typer.echo(f"\n  {icon}  {_c(pathlib.Path(path).name, '1')}")
        typer.echo(f"     captured : {captured}")
        if scrubbed:
            typer.echo(f"     scrubbed : {_c(', '.join(scrubbed), '33')}")
    typer.echo("")


# ── show ──────────────────────────────────────────────────────────────────────

@app.command("show")
def show_fixture(
    name: str = typer.Argument(..., help="Fixture name."),
    output_dir: Optional[pathlib.Path] = typer.Option(None, "--dir", "-d"),
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


# ── diff ──────────────────────────────────────────────────────────────────────

@app.command("diff")
def diff_fixture(
    name: str = typer.Argument(..., help="Fixture name to diff."),
    output_dir: Optional[pathlib.Path] = typer.Option(None, "--dir", "-d"),
    mode: str = typer.Option(
        "structural", "--mode", "-m",
        help="Diff mode: 'structural' (field paths) or 'source' (raw Python).",
    ),
) -> None:
    """
    Show what changed between the last two captures of a fixture.

    Exits with code 1 if differences are found (CI-safe).
    """
    store = _store(output_dir)
    if not store.exists(name):
        typer.echo(f"No fixture named '{name}'.", err=True)
        raise typer.Exit(1)
    if not store.has_snapshot(name):
        typer.echo(f"No snapshot for '{name}'. Capture it twice to enable diffing.")
        raise typer.Exit(0)

    try:
        current = store._snapshots.load(name)
    except Exception as e:
        typer.echo(f"Could not load snapshot: {e}", err=True)
        raise typer.Exit(1)

    prev_path = store._snapshots._path(name).with_suffix(".prev.json")
    if not prev_path.exists():
        typer.echo(
            f"Only one snapshot for '{name}'. Re-capture to generate a second."
        )
        raise typer.Exit(0)

    import json as _json
    from snapfix.diff import structural_diff, source_diff
    prev = _json.loads(prev_path.read_text())
    diff_str = structural_diff(prev, current, name) if mode == "structural" else source_diff(str(prev), str(current), name)

    if not diff_str:
        typer.echo(_c(f"✓  No structural changes in '{name}'", "32"))
        raise typer.Exit(0)

    typer.echo(_c(f"✗  Changes detected in '{name}':", "31"))
    typer.echo("")
    for line in diff_str.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            typer.echo(_c(line, "32"))
        elif line.startswith("-") and not line.startswith("---"):
            typer.echo(_c(line, "31"))
        elif line.startswith("@@"):
            typer.echo(_c(line, "36"))
        else:
            typer.echo(line)
    typer.echo("")
    raise typer.Exit(1)


# ── audit ─────────────────────────────────────────────────────────────────────

@app.command("audit")
def audit_fixtures(
    output_dir: Optional[pathlib.Path] = typer.Option(
        None, "--dir", "-d", help="Fixture directory (default: from config)."
    ),
    strict: bool = typer.Option(
        False, "--strict", "-s",
        help="Exit 1 on any finding. Use in CI / pre-commit hooks.",
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q",
        help="Only print findings, not the full report.",
    ),
) -> None:
    """
    Scan fixture files for PII that may have been missed by field-name scrubbing.

    Checks for: email addresses, phone numbers, SSNs, credit card numbers,
    AWS access keys, and long API key-like strings.

    Exit codes:
      0 — no findings (or findings exist but --strict not set)
      1 — findings detected with --strict
      2 — no fixture files found

    Pre-commit hook configuration (.pre-commit-config.yaml):
    \\b
        - repo: local
          hooks:
            - id: snapfix-audit
              name: snapfix PII audit
              entry: snapfix audit --strict
              language: system
              files: ^tests/fixtures/snapfix_.*\\.py$
    """
    directory = output_dir or _default_dir()

    if not directory.exists():
        typer.echo(f"Directory not found: {directory}", err=True)
        raise typer.Exit(2)

    result = scan_directory(directory)

    if result.files_scanned == 0:
        typer.echo("No fixture files found.")
        raise typer.Exit(2)

    if not quiet:
        typer.echo(format_audit_report(result, directory))
    elif not result.passed:
        for finding in result.findings:
            typer.echo(str(finding))

    if not result.passed and strict:
        raise typer.Exit(1)


# ── verify ────────────────────────────────────────────────────────────────────

@app.command("verify")
def verify_fixtures(
    output_dir: Optional[pathlib.Path] = typer.Option(
        None, "--dir", "-d", help="Fixture directory (default: from config)."
    ),
    strict: bool = typer.Option(
        False, "--strict", "-s",
        help="Fail on sentinel markers (truncated, circular, unserializable).",
    ),
) -> None:
    """
    Verify all fixture files: confirm they import correctly and return valid data.

    Checks each fixture for:
      • Valid Python syntax
      • Importable without errors
      • Fixture function is callable
      • Returns a non-error value
      • No truncated/circular sentinels (with --strict)

    Exit codes:
      0 — all fixtures valid
      1 — one or more fixtures failed
      2 — no fixture files found
    """
    directory = output_dir or _default_dir()

    if not directory.exists():
        typer.echo(f"Directory not found: {directory}", err=True)
        raise typer.Exit(2)

    results = verify_directory(directory, strict=strict)

    if not results:
        typer.echo("No fixture files found.")
        raise typer.Exit(2)

    typer.echo(format_verify_report(results, directory))

    failed = [r for r in results if not r.passed]
    if failed:
        raise typer.Exit(1)


# ── clear ─────────────────────────────────────────────────────────────────────

@app.command("clear")
def clear_fixture(
    name: str = typer.Argument(..., help="Fixture name to delete."),
    output_dir: Optional[pathlib.Path] = typer.Option(None, "--dir", "-d"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete a captured fixture and its snapshot."""
    store = _store(output_dir)
    if not store.exists(name):
        typer.echo(f"No fixture named '{name}'.", err=True)
        raise typer.Exit(1)
    if not yes:
        typer.confirm(f"Delete fixture '{name}' and its snapshot?", abort=True)
    store.delete(name)
    typer.echo(f"Deleted '{name}'.")


@app.command("clear-all")
def clear_all(
    output_dir: Optional[pathlib.Path] = typer.Option(None, "--dir", "-d"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Delete all captured fixtures and snapshots."""
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


@app.command("snapshots")
def list_snapshots(
    output_dir: Optional[pathlib.Path] = typer.Option(None, "--dir", "-d"),
) -> None:
    """List all stored snapshots (used for diffing)."""
    store = _store(output_dir)
    names = store.snapshot_names()
    if not names:
        typer.echo("No snapshots stored.")
        raise typer.Exit(0)
    typer.echo(f"{len(names)} snapshot(s):")
    for n in names:
        typer.echo(f"  {_c('◉', '32')}  {n}")
