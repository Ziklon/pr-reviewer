import instructor
from anthropic import AsyncAnthropic
from pydantic import BaseModel

from pr_reviewer.schemas import Finding, ReviewOutput, Severity, SubReviewerOutput
from pr_reviewer.settings import MODEL_DEFAULT

_SEVERITY_RANK = {
    Severity.critical: 0,
    Severity.high: 1,
    Severity.medium: 2,
    Severity.low: 3,
    Severity.info: 4,
}

_SYSTEM = (
    "You are a lead engineer synthesizing PR review findings. "
    "Write a concise 2–3 sentence overall assessment of the pull request "
    "based on the findings provided. Be direct and specific."
)


class _Summary(BaseModel):
    summary: str


def _deduplicate(findings: list[Finding]) -> list[Finding]:
    """Remove near-duplicate findings by (file, line_range, category)."""
    seen: set[tuple] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.file, f.line_range, f.category)
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def _rank(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda f: (_SEVERITY_RANK[f.severity], -f.confidence),
    )


async def synthesize(
    sub_outputs: list[SubReviewerOutput],
    pr_url: str,
    client: AsyncAnthropic,
    total_cost_usd: float | None = None,
    model: str = MODEL_DEFAULT,
) -> ReviewOutput:
    """Merge sub-reviewer outputs and produce the final ranked review."""
    all_findings = [f for out in sub_outputs for f in out.findings]
    deduped = _rank(_deduplicate(all_findings))

    # Only ask the LLM for a summary — dedup and ranking are done locally.
    instructor_client = instructor.from_anthropic(client)

    findings_text = "\n".join(
        f"[{f.severity.value.upper()}] {f.category.value} | {f.file}:{f.line_range} — {f.issue}"
        for f in deduped
    )

    result = await instructor_client.chat.completions.create(
        model=model,
        max_tokens=512,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"PR: {pr_url}\n\n"
                    f"Findings ({len(deduped)} total):\n{findings_text}\n\n"
                    "Write a 2–3 sentence summary of the overall PR quality."
                ),
            }
        ],
        response_model=_Summary,
    )

    return ReviewOutput(
        pr_url=pr_url,
        findings=deduped,
        summary=result.summary,
        cost_usd=total_cost_usd,
    )
