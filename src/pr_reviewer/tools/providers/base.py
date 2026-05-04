from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PRMetadata:
    title: str
    body: str
    author: str
    base_branch: str
    head_branch: str
    changed_files: int
    additions: int
    deletions: int


@dataclass
class CredentialInfo:
    env_var: str
    description: str
    required: bool
    configured: bool


class GitProvider(ABC):
    """Abstract base for a git-hosting provider (GitHub, GitLab, Azure DevOps, …)."""

    @classmethod
    @abstractmethod
    def supports(cls, url: str) -> bool:
        """Return True if this provider can handle the given PR/MR URL."""

    @classmethod
    @abstractmethod
    def credentials(cls) -> list[CredentialInfo]:
        """Return the credential requirements and their current status."""

    @abstractmethod
    def fetch_diff(self, pr_url: str) -> str:
        """Return the unified diff for the pull/merge request."""

    @abstractmethod
    def fetch_metadata(self, pr_url: str) -> PRMetadata:
        """Return structured metadata for the pull/merge request."""
