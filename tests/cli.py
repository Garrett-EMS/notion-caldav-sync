"""Typer-powered front-end for running the integration test suite."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pytest
import typer


app = typer.Typer(help="Run live integration tests against Notion and iCloud CalDAV.")


def _resolve_pytest_args(
    suite: str,
    env_file: Optional[Path],
    keyword: Optional[str],
    extra: List[str],
    verbose: bool,
) -> List[str]:
    args: List[str] = []
    marker = None
    suite_expression = None
    if suite == "integration":
        marker = "integration"
    elif suite == "smoke":
        suite_expression = "environment or discovery or notion"
    if marker:
        args.extend(["-m", marker])
    combined_expression = suite_expression
    if keyword:
        combined_expression = f"({suite_expression}) and ({keyword})" if suite_expression else keyword
    if combined_expression:
        args.extend(["-k", combined_expression])
    if env_file:
        args.extend(["--env-file", str(env_file)])
    if verbose:
        args.append("-vv")
    args.extend(extra)
    args.append("tests")
    return args


@app.command("run")
def run_suite(
    suite: str = typer.Option(
        "integration",
        help="Which suite to run (integration|smoke|all).",
    ),
    env_file: Optional[Path] = typer.Option(
        None,
        help="Optional path to the .env file with live credentials.",
    ),
    keyword: Optional[str] = typer.Option(None, "-k", help="Pytest expression to filter tests."),
    verbose: bool = typer.Option(False, "-v", help="Run pytest with -vv."),
    extra: List[str] = typer.Argument(default_factory=list),
) -> None:
    if suite not in {"integration", "smoke", "all"}:
        raise typer.BadParameter("suite must be integration, smoke, or all")
    args = _resolve_pytest_args(suite, env_file, keyword, extra, verbose)
    exit_code = pytest.main(args)
    raise typer.Exit(exit_code)


@app.command("full")
def run_full(env_file: Optional[Path] = typer.Option(None), verbose: bool = typer.Option(False)) -> None:
    args = _resolve_pytest_args("integration", env_file, None, [], verbose)
    exit_code = pytest.main(args)
    raise typer.Exit(exit_code)


@app.command("smoke")
def run_smoke(env_file: Optional[Path] = typer.Option(None), verbose: bool = typer.Option(False)) -> None:
    args = _resolve_pytest_args("smoke", env_file, None, [], verbose)
    exit_code = pytest.main(args)
    raise typer.Exit(exit_code)


if __name__ == "__main__":
    app()


