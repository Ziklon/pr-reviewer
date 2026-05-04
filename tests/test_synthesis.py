from pr_reviewer.agents.synthesis import _deduplicate, _rank
from pr_reviewer.schemas import Category, Finding, Severity


def make_finding(
    file="src/app.py",
    line_range=(1, 5),
    severity=Severity.high,
    category=Category.security,
    confidence=0.9,
) -> Finding:
    return Finding(
        file=file,
        line_range=line_range,
        severity=severity,
        category=category,
        issue="test issue",
        suggested_fix="test fix",
        confidence=confidence,
        reasoning="test reasoning",
    )


class TestDeduplicate:
    def test_removes_exact_duplicate(self):
        f1 = make_finding()
        f2 = make_finding()
        assert len(_deduplicate([f1, f2])) == 1

    def test_keeps_different_files(self):
        f1 = make_finding(file="a.py")
        f2 = make_finding(file="b.py")
        assert len(_deduplicate([f1, f2])) == 2

    def test_keeps_different_line_ranges(self):
        f1 = make_finding(line_range=(1, 5))
        f2 = make_finding(line_range=(10, 20))
        assert len(_deduplicate([f1, f2])) == 2

    def test_keeps_different_categories(self):
        f1 = make_finding(category=Category.security)
        f2 = make_finding(category=Category.performance)
        assert len(_deduplicate([f1, f2])) == 2

    def test_preserves_first_occurrence(self):
        f1 = make_finding(confidence=0.9)
        f2 = make_finding(confidence=0.5)
        result = _deduplicate([f1, f2])
        assert result[0].confidence == 0.9

    def test_empty_input(self):
        assert _deduplicate([]) == []

    def test_single_finding_unchanged(self):
        f = make_finding()
        assert _deduplicate([f]) == [f]


class TestRank:
    def test_critical_before_high(self):
        high = make_finding(severity=Severity.high, file="a.py")
        critical = make_finding(severity=Severity.critical, file="b.py")
        result = _rank([high, critical])
        assert result[0].severity == Severity.critical

    def test_full_severity_order(self):
        findings = [
            make_finding(severity=s, file=s.value)
            for s in [Severity.info, Severity.low, Severity.medium, Severity.high, Severity.critical]
        ]
        result = _rank(findings)
        expected_order = [
            Severity.critical, Severity.high, Severity.medium, Severity.low, Severity.info
        ]
        assert [f.severity for f in result] == expected_order

    def test_higher_confidence_first_within_same_severity(self):
        low_conf = make_finding(confidence=0.5, file="a.py")
        high_conf = make_finding(confidence=0.95, file="b.py")
        result = _rank([low_conf, high_conf])
        assert result[0].confidence == 0.95

    def test_empty_input(self):
        assert _rank([]) == []

    def test_single_finding_unchanged(self):
        f = make_finding()
        assert _rank([f]) == [f]
