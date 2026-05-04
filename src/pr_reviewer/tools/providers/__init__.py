from enum import Enum

from .base import CredentialInfo, GitProvider, PRMetadata
from .github import GitHubProvider


class ProviderType(str, Enum):
    github = "github"
    # gitlab = "gitlab"   # add providers/gitlab.py + entry below
    # azure = "azure"     # add providers/azure.py  + entry below


# Maps enum values to concrete classes. To support a new provider:
#   1. Create providers/<name>.py implementing GitProvider
#   2. Import it above
#   3. Add an entry here
_REGISTRY: dict[ProviderType, type[GitProvider]] = {
    ProviderType.github: GitHubProvider,
}

# Singleton cache — one instance per ProviderType.
# Providers are stateless, so sharing instances is safe.
_instances: dict[ProviderType, GitProvider] = {}


def create_provider(provider_type: ProviderType) -> GitProvider:
    """Return the singleton instance for the given provider type."""
    if provider_type not in _instances:
        cls = _REGISTRY.get(provider_type)
        if cls is None:
            raise ValueError(f"Provider not implemented: {provider_type!r}")
        _instances[provider_type] = cls()
    return _instances[provider_type]


def _detect_provider_type(url: str) -> ProviderType:
    for pt, cls in _REGISTRY.items():
        if cls.supports(url):
            return pt
    supported = ", ".join(pt.value for pt in _REGISTRY)
    raise ValueError(
        f"No provider found for URL: {url!r}. "
        f"Supported providers: {supported}"
    )


def get_provider(url: str) -> GitProvider:
    """Auto-detect and return the singleton provider for a PR URL."""
    return create_provider(_detect_provider_type(url))


__all__ = [
    "CredentialInfo",
    "GitProvider",
    "PRMetadata",
    "ProviderType",
    "create_provider",
    "get_provider",
]
