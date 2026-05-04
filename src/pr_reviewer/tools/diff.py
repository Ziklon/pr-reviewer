import subprocess
from pathlib import Path


def read_diff_file(path: str) -> str:
    """Read a unified diff from a file on disk."""
    return Path(path).read_text()


def get_local_diff(base: str = "main") -> str:
    """Return the unified diff of HEAD vs base branch."""
    result = subprocess.run(
        ["git", "diff", base],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def get_staged_diff() -> str:
    """Return the unified diff of staged changes."""
    result = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
