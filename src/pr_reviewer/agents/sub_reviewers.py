import instructor
from anthropic import AsyncAnthropic

from pr_reviewer.schemas import Category, SubReviewerOutput
from pr_reviewer.settings import MODEL_DEFAULT

_MAX_FINDINGS = 5

_SYSTEM_PROMPTS: dict[Category, str] = {
    Category.security: (
        "You are a senior security engineer reviewing a pull request diff. "
        "Focus exclusively on security vulnerabilities: injection attacks, hardcoded secrets, "
        "insecure deserialization, missing auth checks, and unsafe crypto usage. "
        f"Return at most {_MAX_FINDINGS} findings, prioritised by severity. Only report genuine issues — avoid noise."
    ),
    Category.performance: (
        "You are a senior performance engineer reviewing a pull request diff. "
        "Focus exclusively on performance issues: N+1 queries, missing indexes, unbounded loops, "
        "blocking I/O in async contexts, and memory leaks. "
        f"Return at most {_MAX_FINDINGS} findings, prioritised by severity. Only report issues with measurable impact."
    ),
    Category.correctness: (
        "You are a senior software engineer reviewing a pull request diff for correctness. "
        "Focus exclusively on bugs: off-by-one errors, unhandled error paths, race conditions, "
        "incorrect null handling, and logic errors. "
        f"Return at most {_MAX_FINDINGS} findings, prioritised by severity. Only report clear defects, not style preferences."
    ),
    Category.style: (
        "You are a senior software engineer reviewing a pull request diff for code quality. "
        "Focus on maintainability: oversized functions, duplicated logic, misleading names, "
        "missing public API docstrings, and inconsistent error handling. "
        f"Return at most {_MAX_FINDINGS} findings, prioritised by severity. Only flag issues that will cause real maintenance pain."
    ),
}

_USER_PROMPT = """\
Review the following PR diff and return your findings.

PR context:
{context}

Diff:
```diff
{diff}
```
"""


async def run_sub_reviewer(
    category: Category,
    diff: str,
    context: str,
    cached_messages: list[dict],
    client: AsyncAnthropic,
    model: str = MODEL_DEFAULT,
) -> SubReviewerOutput:
    """Run a single sub-reviewer agent. cached_messages carries the prompt-cached diff block."""
    instructor_client = instructor.from_anthropic(client)

    # The diff is already in cached_messages as a cache_control block.
    # We append just the category-specific instruction.
    messages = cached_messages + [
        {
            "role": "user",
            "content": f"Now perform the {category.value} review only and return your structured findings.",
        }
    ]

    result = await instructor_client.chat.completions.create(
        model=model,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPTS[category],
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=messages,
        response_model=SubReviewerOutput,
    )
    result.category = category
    return result


def build_cached_messages(diff: str, context: str) -> list[dict]:
    """Build the shared user message with cache_control on the diff block."""
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"PR context:\n{context}\n\nDiff:",
                },
                {
                    "type": "text",
                    "text": f"```diff\n{diff}\n```",
                    "cache_control": {"type": "ephemeral"},
                },
            ],
        }
    ]
