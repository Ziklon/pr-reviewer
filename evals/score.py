#!/usr/bin/env python3
"""
Score eval results against human-labeled ground truth.

Metrics:
  recall@canonical  — did the agent catch each PR's primary human finding?
  recall@all        — did the agent catch every human finding across all PRs?
  category_acc      — fraction of agent findings in the PR's expected category
  top_cat_match     — does the top-ranked agent finding match the PR's category?
  avg_findings      — average number of agent findings per PR
  avg_cost_usd      — average cost per review (if tracked)

Match criteria (loose):  category == category
Match criteria (strict): category == category AND file basename matches

Usage:
    uv run evals/score.py
    uv run evals/score.py --results-dir evals/results --strict
"""
import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

REPO_ROOT = Path(__file__).parent.parent
LABELS_FILE = REPO_ROOT / "evals" / "labels.json"
RESULTS_DIR = REPO_ROOT / "evals" / "results"

console = Console()
app = typer.Typer(add_completion=False)

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

_STOP = {
    "a", "an", "the", "is", "in", "of", "to", "and", "or", "for", "with",
    "when", "on", "at", "by", "be", "are", "was", "not", "that", "this",
    "it", "as", "from", "if", "via", "its", "but", "can", "has", "have",
    "do", "so", "no", "all", "any", "used", "using", "use", "into",
}


def _keywords(text: str) -> set[str]:
    tokens = set(text.lower().replace(",", " ").replace(".", " ").replace("(", " ").replace(")", " ").split())
    return tokens - _STOP


def _file_base(path: str) -> str:
    return Path(path).name


def _matches(agent: dict, human: dict, strict: bool) -> bool:
    """Return True if agent finding covers the human finding."""
    if agent["category"] != human["category"]:
        return False
    if strict and _file_base(agent["file"]) != _file_base(human["file"]):
        return False
    # Keyword overlap check (loose semantic match)
    a_kw = _keywords(agent["issue"])
    h_kw = _keywords(human["issue"])
    overlap = a_kw & h_kw
    return len(overlap) >= 2  # at least 2 non-trivial shared keywords


def _top_finding(findings: list[dict]) -> dict | None:
    if not findings:
        return None
    return min(
        findings,
        key=lambda f: (_SEVERITY_RANK.get(f["severity"], 99), -f.get("confidence", 0)),
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_pr(result: dict, label: dict, strict: bool) -> dict:
    agent_findings = result.get("findings", [])
    human_findings = label.get("human_findings", [])
    expected_category = label["category"]

    # recall@canonical — primary human finding (index 0)
    canonical_caught = False
    if human_findings:
        canonical = human_findings[0]
        canonical_caught = any(_matches(a, canonical, strict) for a in agent_findings)

    # recall@all — every human finding
    all_caught = []
    for hf in human_findings:
        caught = any(_matches(a, hf, strict) for a in agent_findings)
        all_caught.append(caught)
    recall_all = sum(all_caught) / len(all_caught) if all_caught else 0.0

    # category_acc — fraction of agent findings in expected category
    cat_acc = (
        sum(1 for f in agent_findings if f["category"] == expected_category) / len(agent_findings)
        if agent_findings else 0.0
    )

    # top_cat_match — top finding category matches expected
    top = _top_finding(agent_findings)
    top_cat_match = (top["category"] == expected_category) if top else False

    # precision — fraction of agent findings that match any human finding
    # (lower bound: undercounts because our labels are not exhaustive)
    true_positives = sum(
        1 for af in agent_findings
        if any(_matches(af, hf, strict=False) for hf in human_findings)
    )
    precision = true_positives / len(agent_findings) if agent_findings else 0.0

    return {
        "id": label["id"],
        "expected_category": expected_category,
        "n_human": len(human_findings),
        "n_agent": len(agent_findings),
        "canonical_caught": canonical_caught,
        "recall_all": recall_all,
        "precision": precision,
        "category_acc": cat_acc,
        "top_cat_match": top_cat_match,
        "cost_usd": result.get("cost_usd"),
        "elapsed_s": result.get("elapsed_s"),
        "model": result.get("model", "unknown"),
    }


def _pct(v: float) -> str:
    return f"{v * 100:.0f}%"


def _avg(vals: list) -> float:
    clean = [v for v in vals if v is not None]
    return sum(clean) / len(clean) if clean else 0.0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@app.command()
def main(
    results_dir: Path = typer.Option(RESULTS_DIR, "--results-dir", "-r"),
    strict: bool = typer.Option(False, "--strict", help="Require file basename match in addition to category"),
    show_findings: bool = typer.Option(False, "--findings", "-f", help="Print agent findings for each PR"),
) -> None:
    labels_raw: list[dict] = json.loads(LABELS_FILE.read_text())
    labels = {l["id"]: l for l in labels_raw}

    result_files = sorted(results_dir.glob("*.json"))
    if not result_files:
        console.print(f"[red]No results found in {results_dir}[/red]")
        console.print("Run [bold]uv run evals/run_eval.py[/bold] first.")
        raise typer.Exit(1)

    scored: list[dict] = []
    missing: list[str] = []
    for path in result_files:
        pr_id = path.stem
        if pr_id not in labels:
            console.print(f"[yellow]Warning: no label for {pr_id}, skipping.[/yellow]")
            continue
        result = json.loads(path.read_text())
        scored.append(score_pr(result, labels[pr_id], strict))

    # Per-PR table
    mode = "strict" if strict else "loose"
    table = Table(title=f"Per-PR scores  (match={mode})", show_lines=True)
    table.add_column("PR", style="cyan", no_wrap=True)
    table.add_column("Cat", justify="center")
    table.add_column("Canonical\ncaught", justify="center")
    table.add_column("Recall\n@all", justify="right")
    table.add_column("Precision\n(lower bd)", justify="right")
    table.add_column("Cat\nacc", justify="right")
    table.add_column("Top\ncat✓", justify="center")
    table.add_column("Agent\nfindings", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Time", justify="right")

    for s in scored:
        table.add_row(
            s["id"],
            s["expected_category"][:4],
            "[green]✓[/green]" if s["canonical_caught"] else "[red]✗[/red]",
            _pct(s["recall_all"]),
            _pct(s["precision"]),
            _pct(s["category_acc"]),
            "[green]✓[/green]" if s["top_cat_match"] else "[red]✗[/red]",
            str(s["n_agent"]),
            f"${s['cost_usd']:.4f}" if s["cost_usd"] else "n/a",
            f"{s['elapsed_s']:.1f}s" if s["elapsed_s"] else "n/a",
        )

    console.print(table)

    # Aggregate metrics
    n = len(scored)
    recall_canonical = _avg([1.0 if s["canonical_caught"] else 0.0 for s in scored])
    recall_all = _avg([s["recall_all"] for s in scored])
    precision = _avg([s["precision"] for s in scored])
    cat_acc = _avg([s["category_acc"] for s in scored])
    top_cat = _avg([1.0 if s["top_cat_match"] else 0.0 for s in scored])
    avg_findings = _avg([s["n_agent"] for s in scored])
    avg_cost = _avg([s["cost_usd"] for s in scored])
    total_cost = sum(s["cost_usd"] for s in scored if s["cost_usd"])

    agg = Table(title="Aggregate metrics", show_header=False, show_lines=True)
    agg.add_column("Metric", style="bold")
    agg.add_column("Value", justify="right")

    agg.add_row("PRs evaluated", str(n))
    agg.add_row("Model", scored[0]["model"] if scored else "—")
    agg.add_row("Recall@canonical", _pct(recall_canonical))
    agg.add_row("Recall@all findings", _pct(recall_all))
    agg.add_row("Precision (lower bound)", _pct(precision))
    agg.add_row("Category accuracy", _pct(cat_acc))
    agg.add_row("Top-finding cat match", _pct(top_cat))
    agg.add_row("Avg findings per PR", f"{avg_findings:.1f}")
    agg.add_row("Avg cost per review", f"${avg_cost:.4f}" if avg_cost else "n/a")
    agg.add_row("Total cost", f"${total_cost:.4f}" if total_cost else "n/a")

    console.print(agg)

    # Optionally dump all agent findings per PR
    if show_findings:
        for path in result_files:
            pr_id = path.stem
            if pr_id not in labels:
                continue
            result = json.loads(path.read_text())
            console.rule(f"[bold]{pr_id}[/bold]")
            for f in result.get("findings", []):
                console.print(
                    f"  [{f['severity'].upper()}] {f['category']} | {f['file']}:{f['line_range']} — {f['issue'][:100]}"
                )

    # Human-readable interpretation
    console.print()
    if recall_canonical >= 0.8:
        console.print("[green]✓ Recall@canonical ≥ 80% — agent catches primary issues reliably.[/green]")
    elif recall_canonical >= 0.6:
        console.print("[yellow]△ Recall@canonical 60–79% — agent misses some key issues.[/yellow]")
    else:
        console.print("[red]✗ Recall@canonical < 60% — agent misses most canonical issues.[/red]")

    if precision >= 0.5:
        console.print("[green]✓ Precision ≥ 50% — most findings map to known issues.[/green]")
    else:
        console.print("[yellow]△ Precision < 50% — many findings are unverified (labels may be incomplete).[/yellow]")
    console.print()


if __name__ == "__main__":
    app()
