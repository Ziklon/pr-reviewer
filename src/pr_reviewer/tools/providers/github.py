import os

import httpx

from .base import CredentialInfo, GitProvider, PRMetadata


class GitHubProvider(GitProvider):
    """Provider for github.com pull requests."""

    _HOST = "github.com"

    @classmethod
    def supports(cls, url: str) -> bool:
        return cls._HOST in url

    @classmethod
    def credentials(cls) -> list[CredentialInfo]:
        return [
            CredentialInfo(
                env_var="GITHUB_TOKEN",
                description="Personal access token (raises rate limit from 60 to 5000 req/hr)",
                required=False,
                configured=bool(os.environ.get("GITHUB_TOKEN")),
            )
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_url(self, url: str) -> tuple[str, str, int]:
        """Return (owner, repo, pr_number) from a GitHub PR URL."""
        parts = url.rstrip("/").split("/")
        # https://github.com/{owner}/{repo}/pull/{number}
        if len(parts) < 7 or parts[5] != "pull":
            raise ValueError(f"Not a valid GitHub PR URL: {url}")
        return parts[3], parts[4], int(parts[6])

    def _headers(self, accept: str) -> dict[str, str]:
        headers = {"Accept": accept}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    # ------------------------------------------------------------------
    # GitProvider interface
    # ------------------------------------------------------------------

    def fetch_diff(self, pr_url: str) -> str:
        owner, repo, number = self._parse_url(pr_url)
        response = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
            headers=self._headers("application/vnd.github.v3.diff"),
            follow_redirects=True,
            timeout=30,
        )
        response.raise_for_status()
        return response.text

    def fetch_metadata(self, pr_url: str) -> PRMetadata:
        owner, repo, number = self._parse_url(pr_url)
        response = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
            headers=self._headers("application/vnd.github.v3+json"),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return PRMetadata(
            title=data.get("title", ""),
            body=data.get("body", "") or "",
            author=data.get("user", {}).get("login", ""),
            base_branch=data.get("base", {}).get("ref", ""),
            head_branch=data.get("head", {}).get("ref", ""),
            changed_files=data.get("changed_files", 0),
            additions=data.get("additions", 0),
            deletions=data.get("deletions", 0),
        )
