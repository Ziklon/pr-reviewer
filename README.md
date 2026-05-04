# PR Reviewer

Multi-agent pull request reviewer powered by the Anthropic SDK. Four parallel sub-reviewers (security, performance, correctness, style) analyse a PR diff simultaneously, then a synthesis agent deduplicates and ranks the findings by severity.

## Architecture

```
                        ┌─────────────────┐
                        │   Supervisor    │
                        │  (orchestrator) │
                        └────────┬────────┘
                 prompt-cached diff shared across all agents
          ┌──────────┬──────────┬──────────┐
          ▼          ▼          ▼          ▼
     Security   Performance Correctness  Style
     reviewer    reviewer    reviewer   reviewer
          └──────────┴──────────┴──────────┘
                        │ findings
                        ▼
                  ┌───────────┐
                  │ Synthesis │  dedup · rank · summarise
                  └───────────┘
```

**Stack:** Python 3.12 · Anthropic SDK · Instructor + Pydantic · Typer · asyncio

## Setup

```bash
# 1. Clone and install
git clone <repo-url>
cd pr-reviewer
uv sync

# 2. Set credentials
cp .env.example .env
# edit .env — add ANTHROPIC_API_KEY and GITHUB_TOKEN
```

## Usage

### Review a GitHub PR

```bash
uv run pr-review review https://github.com/owner/repo/pull/42
```

### Review from a local diff file

```bash
git diff main > my-changes.diff
uv run pr-review review --diff my-changes.diff
```

### Review staged / local changes against a branch

```bash
uv run pr-review review --base main
```

### Output as JSON

```bash
uv run pr-review review https://github.com/owner/repo/pull/42 --output json
```

### Use a custom rule set

```bash
uv run pr-review review https://github.com/owner/repo/pull/42 --config config/rules.yaml
```

### Run the eval suite

```bash
uv run pr-review eval --labels evals/labels.json
```

## Development

### Run all tests

```bash
uv run pytest
```

Verbose output with individual test names:

```bash
uv run pytest -v
```

Run a specific test file:

```bash
uv run pytest tests/test_providers.py -v
```

## Output

Each finding includes:

| Field | Description |
|---|---|
| `file` | File path relative to repo root |
| `line_range` | `(start, end)` lines in the diff |
| `severity` | `critical` · `high` · `medium` · `low` · `info` |
| `category` | `security` · `performance` · `correctness` · `style` |
| `issue` | Concise description of the problem |
| `suggested_fix` | Concrete recommendation |
| `confidence` | 0–1 reviewer confidence score |
| `reasoning` | Why it's a problem, citing diff lines |

## Adding a provider

Only GitHub is supported today. To add GitLab, Azure DevOps, or any other host:

1. Create `src/pr_reviewer/tools/providers/<name>.py` implementing `GitProvider`
2. Add a `ProviderType.<name>` entry to the enum in `providers/__init__.py`
3. Register the class in `_REGISTRY`

```python
# providers/__init__.py
from .gitlab import GitLabProvider

class ProviderType(str, Enum):
    github = "github"
    gitlab = "gitlab"   # new

_REGISTRY = {
    ProviderType.github: GitHubProvider,
    ProviderType.gitlab: GitLabProvider,  # new
}
```
