import json
import os
import stat
from pathlib import Path

AUTH_FILE = Path.home() / ".local" / "share" / "pr-reviewer" / "auth.json"


def load_auth() -> dict[str, str]:
    if not AUTH_FILE.exists():
        return {}
    return json.loads(AUTH_FILE.read_text())


def save_auth(credentials: dict[str, str]) -> None:
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps(credentials, indent=2))
    AUTH_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 600


def inject_auth() -> None:
    """Load stored credentials into os.environ without overriding existing env vars."""
    for key, value in load_auth().items():
        if key not in os.environ:
            os.environ[key] = value


def credential_source(env_var: str) -> str:
    """Return where a credential is currently coming from."""
    if os.environ.get(env_var):
        stored = load_auth().get(env_var)
        if stored and os.environ[env_var] == stored:
            return "auth file"
        return "env var"
    return "not set"
