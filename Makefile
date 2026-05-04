.PHONY: eval score eval-fast eval-haiku review clean-results help

# Run the full eval (all 9 PRs, sonnet, sequential)
eval:
	uv run evals/run_eval.py

# Run eval with concurrency for speed
eval-fast:
	uv run evals/run_eval.py --concurrency 3

# Run eval with haiku (cheaper, ~10x less cost)
eval-haiku:
	uv run evals/run_eval.py --model claude-haiku-4-5-20251001

# Score the last eval run
score:
	uv run evals/score.py

# Score with strict file matching
score-strict:
	uv run evals/score.py --strict

# Score and dump all agent findings
score-verbose:
	uv run evals/score.py --findings

# Run eval then immediately score
eval-and-score:
	uv run evals/run_eval.py && uv run evals/score.py

# Review a single local diff
# Usage: make review DIFF=path/to/file.diff
review:
	uv run pr-review diff $(DIFF)

# Remove all cached results
clean-results:
	rm -rf evals/results/

# Run tests
test:
	uv run pytest

help:
	@echo ""
	@echo "  make eval            Run full eval (9 PRs, sonnet)"
	@echo "  make eval-fast       Run eval with concurrency=3"
	@echo "  make eval-haiku      Run eval with haiku (cheaper)"
	@echo "  make eval-and-score  Run eval then score in one shot"
	@echo "  make score           Score the last eval run"
	@echo "  make score-strict    Score with file-level matching"
	@echo "  make score-verbose   Score + print all agent findings"
	@echo "  make review DIFF=x   Review a local diff file"
	@echo "  make clean-results   Delete cached results"
	@echo "  make test            Run test suite"
	@echo ""
