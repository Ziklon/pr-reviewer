from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class Category(str, Enum):
    security = "security"
    performance = "performance"
    correctness = "correctness"
    style = "style"


class Finding(BaseModel):
    file: str = Field(description="File path relative to repo root")
    line_range: tuple[int, int] = Field(description="(start_line, end_line) in the diff")
    severity: Severity
    category: Category
    issue: str = Field(description="Concise description of the problem")
    suggested_fix: str = Field(description="Concrete fix or recommendation")
    confidence: float = Field(ge=0.0, le=1.0, description="Reviewer confidence 0–1")
    reasoning: str = Field(description="Why this is a problem, citing specific diff lines")


class SubReviewerOutput(BaseModel):
    category: Category
    findings: list[Finding] = Field(default_factory=list)


class ReviewOutput(BaseModel):
    pr_url: str
    findings: list[Finding] = Field(
        description="Deduplicated findings ranked by severity then confidence"
    )
    summary: str = Field(description="2–3 sentence overall assessment")
    cost_usd: float | None = None
