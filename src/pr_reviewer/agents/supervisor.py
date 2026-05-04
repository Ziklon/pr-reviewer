import asyncio
from collections.abc import Callable

from anthropic import AsyncAnthropic

from pr_reviewer.schemas import Category, ReviewOutput, SubReviewerOutput
from pr_reviewer.settings import MODEL_DEFAULT

from .sub_reviewers import build_cached_messages, run_sub_reviewer
from .synthesis import synthesize

_CATEGORIES = [
    Category.security,
    Category.performance,
    Category.correctness,
    Category.style,
]


async def _run_and_notify(
    category: Category,
    diff: str,
    context: str,
    cached_messages: list[dict],
    client: AsyncAnthropic,
    model: str,
    on_agent_complete: Callable[[SubReviewerOutput], None] | None,
) -> SubReviewerOutput:
    result = await run_sub_reviewer(
        category=category,
        diff=diff,
        context=context,
        cached_messages=cached_messages,
        client=client,
        model=model,
    )
    if on_agent_complete:
        on_agent_complete(result)
    return result


async def review(
    diff: str,
    pr_url: str = "",
    context: str = "",
    model: str = MODEL_DEFAULT,
    on_agent_complete: Callable[[SubReviewerOutput], None] | None = None,
    on_tick: Callable[[], None] | None = None,
) -> ReviewOutput:
    """
    Supervisor entrypoint.

    Builds a shared prompt-cached message block, fans out to 4 parallel
    sub-reviewers, then calls the synthesis agent to produce the final review.
    """
    client = AsyncAnthropic()
    cached_messages = build_cached_messages(diff, context)

    async def _ticker() -> None:
        while True:
            await asyncio.sleep(1)
            if on_tick:
                on_tick()

    ticker_task = asyncio.create_task(_ticker())

    try:
        sub_outputs = await asyncio.gather(
            *[
                _run_and_notify(
                    category=cat,
                    diff=diff,
                    context=context,
                    cached_messages=cached_messages,
                    client=client,
                    model=model,
                    on_agent_complete=on_agent_complete,
                )
                for cat in _CATEGORIES
            ]
        )
    finally:
        ticker_task.cancel()
        try:
            await ticker_task
        except asyncio.CancelledError:
            pass

    return await synthesize(
        sub_outputs=list(sub_outputs),
        pr_url=pr_url,
        client=client,
        model=model,
    )
