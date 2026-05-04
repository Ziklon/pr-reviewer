#!/usr/bin/env python3
"""
Run the PR reviewer agent against the eval dataset.

Usage:
    uv run evals/run_eval.py
    uv run evals/run_eval.py --ids django-django-15198 psf-requests-6667
    uv run evals/run_eval.py --model claude-haiku-4-5-20251001
    uv run evals/run_eval.py --concurrency 3
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

# Allow running from repo root without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pr_reviewer.auth import inject_auth  # noqa: E402
from pr_reviewer.agents.supervisor import review  # noqa: E402

inject_auth()

REPO_ROOT = Path(__file__).parent.parent
LABELS_FILE = REPO_ROOT / "evals" / "labels.json"
RESULTS_DIR = REPO_ROOT / "evals" / "results"

console = Console()
app = typer.Typer(add_completion=False)

# Approximate cost per 1M tokens (claude-sonnet-4-6 pricing)
_COST_PER_M = {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75}


def _estimate_cost(usage: dict) -> float:
    return (
        usage.get("input_tokens", 0) * _COST_PER_M["input"] / 1_000_000
        + usage.get("output_tokens", 0) * _COST_PER_M["output"] / 1_000_000
        + usage.get("cache_read_input_tokens", 0) * _COST_PER_M["cache_read"] / 1_000_000
        + usage.get("cache_creation_input_tokens", 0) * _COST_PER_M["cache_write"] / 1_000_000
    )


async def _run_one(label: dict, model: str, semaphore: asyncio.Semaphore) -> dict:
    pr_id = label["id"]
    diff = (REPO_ROOT / label["diff_file"]).read_text()

    async with semaphore:
        console.print(f"  [cyan]→[/cyan] {pr_id}")
        start = time.monotonic()

        # Accumulate token usage across all sub-calls via a patched client
        usage_totals: dict[str, int] = {}

        _orig_messages_create = None

        try:
            import anthropic as _anthropic

            _orig_create = _anthropic.AsyncAnthropic().messages.create.__func__  # type: ignore[attr-defined]
        except Exception:
            _orig_create = None

        # Patch AsyncAnthropic.messages.create to intercept usage
        import anthropic as _anthropic_mod

        _patched_calls: list[dict] = []

        _orig_cls_create = _anthropic_mod.resources.messages.AsyncMessages.create

        async def _tracking_create(self, *args, **kwargs):  # type: ignore[override]
            resp = await _orig_cls_create(self, *args, **kwargs)
            if hasattr(resp, "usage"):
                u = resp.usage
                _patched_calls.append(
                    {
                        "input_tokens": getattr(u, "input_tokens", 0),
                        "output_tokens": getattr(u, "output_tokens", 0),
                        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0),
                        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0),
                    }
                )
            return resp

        _anthropic_mod.resources.messages.AsyncMessages.create = _tracking_create  # type: ignore[method-assign]

        try:
            output = await review(diff=diff, pr_url=label["pr_url"], model=model)
        finally:
            _anthropic_mod.resources.messages.AsyncMessages.create = _orig_cls_create  # type: ignore[method-assign]

        elapsed = time.monotonic() - start

        for call in _patched_calls:
            for k, v in call.items():
                usage_totals[k] = usage_totals.get(k, 0) + v

        cost = _estimate_cost(usage_totals) if usage_totals else None

        result = {
            "id": pr_id,
            "model": model,
            "elapsed_s": round(elapsed, 2),
            "cost_usd": round(cost, 6) if cost is not None else None,
            "usage": usage_totals,
            **output.model_dump(),
        }

        n = len(output.findings)
        cost_str = f"${cost:.4f}" if cost is not None else "n/a"
        console.print(
            f"    [green]✓[/green] {n} findings  cost={cost_str}  {elapsed:.1f}s"
        )
        return result


@app.command()
def main(
    ids: list[str] = typer.Option([], "--ids", "-i", help="PR IDs to run (default: all)"),
    model: str = typer.Option("claude-sonnet-4-6", "--model", "-m"),
    output_dir: Path = typer.Option(RESULTS_DIR, "--output-dir", "-o"),
    concurrency: int = typer.Option(1, "--concurrency", "-c", help="Parallel PR runs"),
) -> None:
    labels: list[dict] = json.loads(LABELS_FILE.read_text())
    if ids:
        labels = [l for l in labels if l["id"] in ids]

    if not labels:
        console.print("[red]No matching PRs found.[/red]")
        raise typer.Exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(
        f"\n[bold]Eval run[/bold]  model={model}  PRs={len(labels)}  concurrency={concurrency}\n"
    )

    async def _run_all() -> list[dict]:
        sem = asyncio.Semaphore(concurrency)
        tasks = [_run_one(label, model, sem) for label in labels]
        return await asyncio.gather(*tasks)

    results = asyncio.run(_run_all())

    # Save results
    for result in results:
        out = output_dir / f"{result['id']}.json"
        out.write_text(json.dumps(result, indent=2))

    # Summary table
    table = Table(title="Results", show_lines=True)
    table.add_column("PR", style="cyan")
    table.add_column("Findings", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Time", justify="right")

    total_cost = 0.0
    for r in results:
        cost = r.get("cost_usd")
        if cost:
            total_cost += cost
        table.add_row(
            r["id"],
            str(len(r.get("findings", []))),
            f"${cost:.4f}" if cost else "n/a",
            f"{r['elapsed_s']:.1f}s",
        )

    console.print(table)
    console.print(f"\nTotal cost: [bold]${total_cost:.4f}[/bold]")
    console.print(f"Results saved to [dim]{output_dir}[/dim]\n")


if __name__ == "__main__":
    app()
