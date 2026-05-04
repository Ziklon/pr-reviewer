import pytest
from pydantic import ValidationError

from pr_reviewer.schemas import (
    Category,
    Finding,
    ReviewOutput,
    Severity,
    SubReviewerOutput,
)


def make_finding(**overrides) -> Finding:
    defaults = dict(
        file="src/app.py",
        line_range=(10, 20),
        severity=Severity.high,
        category=Category.security,
        issue="SQL injection vulnerability",
        suggested_fix="Use parameterized queries",
        confidence=0.95,
        reasoning="Line 15 concatenates user input directly into SQL",
    )
    defaults.update(overrides)
    return Finding(**defaults)


class TestSeverityEnum:
    def test_all_values_exist(self):
        assert {s.value for s in Severity} == {"critical", "high", "medium", "low", "info"}


class TestCategoryEnum:
    def test_all_values_exist(self):
        assert {c.value for c in Category} == {
            "security", "performance", "correctness", "style"
        }


class TestFinding:
    def test_valid_finding(self):
        f = make_finding()
        assert f.severity == Severity.high
        assert f.category == Category.security
        assert f.confidence == 0.95

    def test_confidence_at_boundaries(self):
        make_finding(confidence=0.0)
        make_finding(confidence=1.0)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValidationError, match="confidence"):
            make_finding(confidence=1.1)

    def test_confidence_below_zero_raises(self):
        with pytest.raises(ValidationError, match="confidence"):
            make_finding(confidence=-0.1)

    def test_invalid_severity_raises(self):
        with pytest.raises(ValidationError):
            make_finding(severity="blocker")

    def test_invalid_category_raises(self):
        with pytest.raises(ValidationError):
            make_finding(category="design")

    def test_severity_accepts_string_alias(self):
        f = make_finding(severity="critical")
        assert f.severity == Severity.critical

    def test_category_accepts_string_alias(self):
        f = make_finding(category="performance")
        assert f.category == Category.performance


class TestSubReviewerOutput:
    def test_empty_findings(self):
        out = SubReviewerOutput(category=Category.security)
        assert out.findings == []

    def test_with_findings(self):
        out = SubReviewerOutput(
            category=Category.performance,
            findings=[make_finding(category=Category.performance)],
        )
        assert len(out.findings) == 1


class TestReviewOutput:
    def test_minimal_valid_output(self):
        out = ReviewOutput(
            pr_url="https://github.com/owner/repo/pull/1",
            findings=[],
            summary="No issues found.",
        )
        assert out.cost_usd is None

    def test_with_cost(self):
        out = ReviewOutput(
            pr_url="https://github.com/owner/repo/pull/1",
            findings=[],
            summary="LGTM",
            cost_usd=0.0412,
        )
        assert out.cost_usd == pytest.approx(0.0412)

    def test_with_findings(self):
        out = ReviewOutput(
            pr_url="https://github.com/owner/repo/pull/1",
            findings=[make_finding(), make_finding(file="other.py", severity=Severity.critical)],
            summary="Two issues found.",
        )
        assert len(out.findings) == 2
