import subprocess
from unittest.mock import MagicMock, patch

import pytest

from pr_reviewer.tools import get_local_diff, get_staged_diff, read_diff_file


class TestReadDiffFile:
    def test_reads_content(self, tmp_path):
        content = "diff --git a/foo.py b/foo.py\n+new line\n"
        f = tmp_path / "changes.diff"
        f.write_text(content)
        assert read_diff_file(str(f)) == content

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_diff_file(str(tmp_path / "nonexistent.diff"))

    def test_empty_file_returns_empty_string(self, tmp_path):
        f = tmp_path / "empty.diff"
        f.write_text("")
        assert read_diff_file(str(f)) == ""


class TestGetLocalDiff:
    def test_returns_stdout(self):
        mock_result = MagicMock()
        mock_result.stdout = "diff --git a/x.py b/x.py\n+change\n"
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = get_local_diff("main")
        assert result == mock_result.stdout
        mock_run.assert_called_once_with(
            ["git", "diff", "main"],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_git_error_raises(self):
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")):
            with pytest.raises(subprocess.CalledProcessError):
                get_local_diff("main")


class TestGetStagedDiff:
    def test_returns_stdout(self):
        mock_result = MagicMock()
        mock_result.stdout = "diff --git a/y.py b/y.py\n+staged\n"
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = get_staged_diff()
        assert result == mock_result.stdout
        mock_run.assert_called_once_with(
            ["git", "diff", "--cached"],
            capture_output=True,
            text=True,
            check=True,
        )
