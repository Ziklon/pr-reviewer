.PHONY: eval eval-sonnet eval-fast score score-strict score-verbose eval-and-score review clean-results test help

HAIKU  = claude-haiku-4-5-20251001
SONNET = claude-sonnet-4-6

# Default eval: haiku (cheap, fast — use for iteration)
eval:
	uv run evals/run_eval.py --model $(HAIKU)

# High-quality eval: sonnet (use for final results / README table)
eval-sonnet:
	uv run evals/run_eval.py --model $(SONNET)

# Run eval with concurrency=3 (haiku by default)
eval-fast:
	uv run evals/run_eval.py --model $(HAIKU) --concurrency 3

# Score the last eval run
score:
	uv run evals/score.py

# Score with strict file-level matching
score-strict:
	uv run evals/score.py --strict

# Score and print all agent findings
score-verbose:
	uv run evals/score.py --findings

# Run eval then immediately score
eval-and-score:
	uv run evals/run_eval.py --model $(HAIKU) && uv run evals/score.py

# Review a single local diff  (usage: make review DIFF=path/to/file.diff)
review:
	uv run pr-review diff $(DIFF)

# Delete cached results
clean-results:
	rm -rf evals/results/

# Run test suite
test:
	uv run pytest

help:
	@echo ""
	@echo "  make eval             Run eval with haiku (~\$$0.02/PR, fast iteration)"
	@echo "  make eval-sonnet      Run eval with sonnet (higher quality, for final results)"
	@echo "  make eval-fast        Run haiku eval with concurrency=3"
	@echo "  make eval-and-score   Eval + score in one shot"
	@echo "  make score            Score the last eval run"
	@echo "  make score-strict     Score with file-level matching"
	@echo "  make score-verbose    Score + print all agent findings"
	@echo "  make review DIFF=x    Review a local diff file"
	@echo "  make clean-results    Delete cached results"
	@echo "  make test             Run test suite"
	@echo ""
