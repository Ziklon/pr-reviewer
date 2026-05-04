from unittest.mock import MagicMock, patch

import pytest

from pr_reviewer.tools import PRMetadata, ProviderType, create_provider, get_provider
from pr_reviewer.tools.providers.github import GitHubProvider


class TestProviderRegistry:
    def test_get_provider_detects_github(self):
        provider = get_provider("https://github.com/owner/repo/pull/42")
        assert isinstance(provider, GitHubProvider)

    def test_get_provider_unknown_url_raises_with_supported_list(self):
        with pytest.raises(ValueError, match="No provider found.*github"):
            get_provider("https://gitlab.com/foo/bar/-/merge_requests/1")

    def test_create_provider_github_enum(self):
        provider = create_provider(ProviderType.github)
        assert isinstance(provider, GitHubProvider)

    def test_create_provider_returns_same_instance(self):
        p1 = create_provider(ProviderType.github)
        p2 = create_provider(ProviderType.github)
        assert p1 is p2

    def test_get_provider_and_create_provider_share_instance(self):
        p1 = create_provider(ProviderType.github)
        p2 = get_provider("https://github.com/owner/repo/pull/1")
        assert p1 is p2


class TestGitHubProviderSupports:
    def test_supports_standard_url(self):
        assert GitHubProvider.supports("https://github.com/owner/repo/pull/42")

    def test_supports_enterprise_github(self):
        assert GitHubProvider.supports("https://github.com/anthropics/sdk/pull/1")

    def test_does_not_support_gitlab(self):
        assert not GitHubProvider.supports("https://gitlab.com/foo/bar/-/merge_requests/1")

    def test_does_not_support_azure(self):
        assert not GitHubProvider.supports(
            "https://dev.azure.com/org/project/_git/repo/pullrequest/1"
        )


class TestGitHubProviderParseUrl:
    def setup_method(self):
        self.provider = GitHubProvider()

    def test_parses_valid_url(self):
        owner, repo, pr_number = self.provider._parse_url(
            "https://github.com/anthropics/anthropic-sdk-python/pull/123"
        )
        assert owner == "anthropics"
        assert repo == "anthropic-sdk-python"
        assert pr_number == 123

    def test_parses_trailing_slash(self):
        owner, repo, pr_number = self.provider._parse_url(
            "https://github.com/owner/repo/pull/7/"
        )
        assert pr_number == 7

    def test_raises_for_issue_url(self):
        with pytest.raises(ValueError, match="Not a valid GitHub PR URL"):
            self.provider._parse_url("https://github.com/owner/repo/issues/42")

    def test_raises_for_bare_repo_url(self):
        with pytest.raises(ValueError, match="Not a valid GitHub PR URL"):
            self.provider._parse_url("https://github.com/owner/repo")


class TestGitHubProviderFetchDiff:
    def setup_method(self):
        self.provider = GitHubProvider()

    def _mock_response(self, text="diff --git a/foo.py b/foo.py\n+hello\n"):
        mock = MagicMock()
        mock.text = text
        mock.raise_for_status = MagicMock()
        return mock

    def test_returns_diff_text(self):
        expected = "diff --git a/foo.py b/foo.py\n+hello\n"
        with patch("httpx.get", return_value=self._mock_response(expected)):
            result = self.provider.fetch_diff("https://github.com/owner/repo/pull/1")
        assert result == expected

    def test_requests_diff_accept_header(self):
        with patch("httpx.get", return_value=self._mock_response()) as mock_get:
            self.provider.fetch_diff("https://github.com/owner/repo/pull/1")
        headers = mock_get.call_args.kwargs["headers"]
        assert "diff" in headers["Accept"]

    def test_injects_auth_header_when_token_set(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test123")
        with patch("httpx.get", return_value=self._mock_response()) as mock_get:
            self.provider.fetch_diff("https://github.com/owner/repo/pull/1")
        headers = mock_get.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer ghp_test123"

    def test_no_auth_header_without_token(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with patch("httpx.get", return_value=self._mock_response()) as mock_get:
            self.provider.fetch_diff("https://github.com/owner/repo/pull/1")
        headers = mock_get.call_args.kwargs["headers"]
        assert "Authorization" not in headers


class TestGitHubProviderFetchMetadata:
    def setup_method(self):
        self.provider = GitHubProvider()

    def _mock_response(self, data: dict):
        mock = MagicMock()
        mock.json.return_value = data
        mock.raise_for_status = MagicMock()
        return mock

    def _sample_data(self, **overrides):
        base = {
            "title": "Fix null pointer",
            "body": "Resolves the crash on startup.",
            "user": {"login": "alice"},
            "base": {"ref": "main"},
            "head": {"ref": "fix/null-pointer"},
            "changed_files": 3,
            "additions": 20,
            "deletions": 5,
        }
        base.update(overrides)
        return base

    def test_returns_pr_metadata(self):
        with patch("httpx.get", return_value=self._mock_response(self._sample_data())):
            meta = self.provider.fetch_metadata("https://github.com/owner/repo/pull/1")

        assert isinstance(meta, PRMetadata)
        assert meta.title == "Fix null pointer"
        assert meta.author == "alice"
        assert meta.base_branch == "main"
        assert meta.head_branch == "fix/null-pointer"
        assert meta.changed_files == 3
        assert meta.additions == 20
        assert meta.deletions == 5

    def test_handles_null_body(self):
        with patch("httpx.get", return_value=self._mock_response(self._sample_data(body=None))):
            meta = self.provider.fetch_metadata("https://github.com/owner/repo/pull/1")
        assert meta.body == ""

    def test_handles_missing_fields_gracefully(self):
        with patch("httpx.get", return_value=self._mock_response({})):
            meta = self.provider.fetch_metadata("https://github.com/owner/repo/pull/1")
        assert meta.title == ""
        assert meta.changed_files == 0
