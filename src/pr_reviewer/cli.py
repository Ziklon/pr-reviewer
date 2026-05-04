import asyncio
import time
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from pr_reviewer.auth import AUTH_FILE, inject_auth, credential_source, load_auth, save_auth

load_dotenv()
inject_auth()  # auth file credentials fill in any gaps not covered by .env or shell env

app = typer.Typer(
    name="pr-review",
    help="Multi-agent PR reviewer — security · performance · correctness · style",
    no_args_is_help=True,
)
console = Console()


class OutputFormat(str, Enum):
    rich = "rich"
    json = "json"


def _render_rich(review) -> None:
    table = Table(title=f"PR Review — {review.pr_url}", show_lines=True)
    table.add_column("Severity", style="bold", width=10)
    table.add_column("Category", width=12)
    table.add_column("File", width=30)
    table.add_column("Lines", width=10)
    table.add_column("Issue")
    table.add_column("Fix")

    severity_colors = {
        "critical": "red",
        "high": "orange3",
        "medium": "yellow",
        "low": "blue",
        "info": "dim",
    }

    for f in review.findings:
        color = severity_colors.get(f.severity.value, "white")
        table.add_row(
            f"[{color}]{f.severity.value}[/{color}]",
            f.category.value,
            f.file,
            f"{f.line_range[0]}–{f.line_range[1]}",
            f.issue,
            f.suggested_fix,
        )

    console.print(table)
    console.print(Panel(review.summary, title="Summary", border_style="green"))
    if review.cost_usd is not None:
        console.print(f"[dim]Cost: ${review.cost_usd:.4f}[/dim]")


@app.command()
def review(
    pr_url: Optional[str] = typer.Argument(None, help="GitHub PR URL to review"),
    diff_file: Optional[Path] = typer.Option(
        None, "--diff", "-d", help="Path to a local .diff file"
    ),
    base: Optional[str] = typer.Option(
        None, "--base", "-b", help="Base branch for local git diff (e.g. main)"
    ),
    thorough: bool = typer.Option(
        False, "--thorough", help="Use Opus for deeper reasoning (higher cost)"
    ),
    output: OutputFormat = typer.Option(OutputFormat.rich, "--output", "-o"),
    config: Path = typer.Option(
        Path("config/rules.yaml"), "--config", "-c", help="Rule set YAML"
    ),
) -> None:
    """Review a pull request and surface findings by category and severity."""
    from pr_reviewer.agents import review as run_review
    from pr_reviewer.settings import MODEL_DEFAULT, MODEL_THOROUGH
    from pr_reviewer.tools import get_local_diff, get_provider, read_diff_file

    model = MODEL_THOROUGH if thorough else MODEL_DEFAULT

    if pr_url:
        provider = get_provider(pr_url)
        provider_name = type(provider).__name__.replace("Provider", "")
        with console.status(f"Fetching PR via {provider_name}..."):
            diff = provider.fetch_diff(pr_url)
            meta = provider.fetch_metadata(pr_url)
            context = (
                f"Title: {meta.title}\n"
                f"Author: {meta.author}\n"
                f"Description: {meta.body[:500]}\n"
                f"Changed files: {meta.changed_files} "
                f"(+{meta.additions} / -{meta.deletions})"
            )
    elif diff_file:
        diff = read_diff_file(str(diff_file))
        context = f"Local diff from file: {diff_file}"
        pr_url = str(diff_file)
    elif base:
        diff = get_local_diff(base)
        context = f"Local diff against branch: {base}"
        pr_url = f"local:{base}"
    else:
        console.print("[red]Provide a PR URL, --diff file, or --base branch.[/red]")
        raise typer.Exit(1)

    if not diff.strip():
        console.print("[yellow]Diff is empty — nothing to review.[/yellow]")
        raise typer.Exit(0)

    # Diff stats
    diff_lines = diff.splitlines()
    n_files = sum(1 for l in diff_lines if l.startswith("diff --git"))
    n_changed = sum(1 for l in diff_lines if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))
    source_label = diff_file.name if diff_file else (pr_url or f"local:{base}")
    console.print(f"[bold]{source_label}[/bold]  [dim]{n_changed} changed lines · {n_files} file{'s' if n_files != 1 else ''}[/dim]\n")

    from pr_reviewer.schemas import Category

    _CATEGORIES = [Category.security, Category.performance, Category.correctness, Category.style]
    agent_status: dict[str, dict] = {cat.value: {"state": "pending", "count": 0} for cat in _CATEGORIES}
    start_time = time.monotonic()

    def _make_live_panel() -> Panel:
        elapsed = int(time.monotonic() - start_time)
        grid = Table.grid(padding=(0, 2))
        grid.add_column(width=2)
        grid.add_column(width=13)
        grid.add_column()
        for cat, info in agent_status.items():
            if info["state"] == "done":
                icon, color = "✓", "green"
                detail = f"[dim]{info['count']} finding{'s' if info['count'] != 1 else ''}[/dim]"
            else:
                icon, color = "⏳", "yellow"
                detail = "[dim]reviewing...[/dim]"
            grid.add_row(f"[{color}]{icon}[/{color}]", f"[{color}]{cat}[/{color}]", detail)
        return Panel(grid, title=f"[bold]Multi-agent review[/bold]  [dim]{model} · {elapsed}s[/dim]", border_style="blue")

    def on_agent_complete(sub_output) -> None:
        agent_status[sub_output.category.value]["state"] = "done"
        agent_status[sub_output.category.value]["count"] = len(sub_output.findings)
        live.update(_make_live_panel())

    def on_tick() -> None:
        live.update(_make_live_panel())

    with Live(_make_live_panel(), console=console, refresh_per_second=4) as live:
        result = asyncio.run(
            run_review(
                diff=diff,
                pr_url=pr_url,
                context=context,
                model=model,
                on_agent_complete=on_agent_complete,
                on_tick=on_tick,
            )
        )

    elapsed_total = int(time.monotonic() - start_time)
    console.print(f"[dim]Completed in {elapsed_total}s[/dim]\n")

    if output == OutputFormat.json:
        console.print_json(result.model_dump_json())
    else:
        _render_rich(result)


@app.command()
def configure() -> None:
    """Interactively set credentials and save them to the auth file."""
    import os

    console.print(f"\nCredentials are stored in [bold]{AUTH_FILE}[/bold] (permissions: 600)\n")
    console.print("Press Enter to keep the current value. Values are masked.\n")

    existing = load_auth()

    def _prompt(label: str, env_var: str, required: bool) -> str | None:
        current = existing.get(env_var) or os.environ.get(env_var, "")
        hint = "(set)" if current else ("required" if required else "optional")
        value = typer.prompt(
            f"  {label} [{hint}]",
            default="",
            hide_input=True,
            show_default=False,
        )
        return value.strip() or current or None

    anthropic_key = _prompt("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY", required=True)
    github_token = _prompt("GITHUB_TOKEN    ", "GITHUB_TOKEN", required=False)

    credentials: dict[str, str] = {}
    if anthropic_key:
        credentials["ANTHROPIC_API_KEY"] = anthropic_key
    if github_token:
        credentials["GITHUB_TOKEN"] = github_token

    save_auth(credentials)
    console.print(f"\n[green]✓ Saved to {AUTH_FILE}[/green]")


@app.command()
def status() -> None:
    """Show configured providers and LLM settings."""
    import os

    from pr_reviewer.settings import MODEL_DEFAULT, MODEL_THOROUGH
    from pr_reviewer.tools.providers import _REGISTRY

    # --- Providers ---
    provider_table = Table(title="Providers", show_header=True, header_style="bold")
    provider_table.add_column("Provider", width=12)
    provider_table.add_column("Credential", width=18)
    provider_table.add_column("Required", width=10)
    provider_table.add_column("Status", width=14)
    provider_table.add_column("Source", width=12)
    provider_table.add_column("Description")

    for pt, cls in _REGISTRY.items():
        for cred in cls.credentials():
            status_str = "[green]✓ set[/green]" if cred.configured else "[yellow]✗ not set[/yellow]"
            required_str = "yes" if cred.required else "optional"
            source = credential_source(cred.env_var) if cred.configured else "—"
            provider_table.add_row(
                pt.value,
                cred.env_var,
                required_str,
                status_str,
                source,
                cred.description,
            )

    console.print(provider_table)

    # --- LLM ---
    api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    api_key_str = "[green]✓ set[/green]" if api_key_set else "[red]✗ not set[/red]"
    api_key_source = credential_source("ANTHROPIC_API_KEY") if api_key_set else "—"

    llm_table = Table(title="LLM", show_header=True, header_style="bold")
    llm_table.add_column("Setting", width=18)
    llm_table.add_column("Value", width=28)
    llm_table.add_column("Source")
    llm_table.add_row("Default model", MODEL_DEFAULT, "pr-review review <url>")
    llm_table.add_row("Thorough model", MODEL_THOROUGH, "pr-review review <url> --thorough")
    llm_table.add_row("ANTHROPIC_API_KEY", api_key_str, api_key_source)

    console.print(llm_table)
    console.print(f"\n[dim]Auth file: {AUTH_FILE}[/dim]")
    console.print("[dim]Run [bold]pr-review configure[/bold] to set credentials.[/dim]")


@app.command()
def eval(
    labels_file: Path = typer.Option(
        Path("evals/labels.json"), "--labels", "-l", help="Human-labeled ground-truth file"
    ),
    output: OutputFormat = typer.Option(OutputFormat.rich, "--output", "-o"),
) -> None:
    """Run the evaluation suite against human-labeled PRs."""
    console.print("[yellow]Eval not yet implemented.[/yellow]")
    raise typer.Exit(0)


if __name__ == "__main__":
    app()
