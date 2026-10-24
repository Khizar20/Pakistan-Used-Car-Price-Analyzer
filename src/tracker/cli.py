"""Command-line interface for the tracker pipeline."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="tracker",
    help="Collect and analyze Pakistan used-car asking prices.",
    no_args_is_help=True,
)


def _future_phase(command: str, phase: int) -> None:
    """Explain why a pipeline command is not available in this phase."""
    typer.echo(f"'{command}' will be implemented in Phase {phase}.", err=True)
    raise typer.Exit(code=2)


@app.command()
def scrape() -> None:
    """Collect public used-car listing data."""
    _future_phase("scrape", 2)


@app.command()
def analyze() -> None:
    """Analyze stored price observations."""
    _future_phase("analyze", 5)


@app.command(name="export")
def export_data() -> None:
    """Export dashboard-ready aggregate data."""
    _future_phase("export", 6)


if __name__ == "__main__":
    app()
