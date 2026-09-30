"""Settings for the MCP server: environment variables first, conf.toml/repos.txt as fallback."""

import os
import re
from pathlib import Path

from dotenv import load_dotenv

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

APP_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = APP_DIR / "conf.toml"
REPOS_FILE = APP_DIR / "repos.txt"

# Keeps GIT_TOKEN out of the MCP client configuration file.
load_dotenv(APP_DIR / ".env")

REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")

DEFAULT_BASE_URL = "https://api.github.com"


class ConfigError(RuntimeError):
    pass


def _toml_github() -> dict:
    if not (CONFIG_FILE.exists() and CONFIG_FILE.stat().st_size > 0):
        return {}
    return tomllib.loads(CONFIG_FILE.read_text()).get("github", {})


def validate_repo(repo: str) -> str:
    repo = repo.strip()
    if not REPO_PATTERN.match(repo):
        raise ConfigError(f"Invalid repository {repo!r}; expected owner/repo")
    return repo


def load_settings() -> dict:
    github = _toml_github()

    token = os.getenv("GIT_TOKEN", "").strip()
    if not token:
        raise ConfigError("GIT_TOKEN is not set for the MCP server")

    base_url = os.getenv("GITHUB_BASE_URL", "").strip() or github.get("base_url") or DEFAULT_BASE_URL
    reviewer = os.getenv("GITHUB_REVIEWER", "").strip() or str(github.get("reviewer", "")).strip()

    return {
        "token": token,
        "base_url": base_url,
        "reviewer": reviewer or None,
        "days_back": int(os.getenv("PR_DAYS_BACK", "") or github.get("days_back", 7)),
        "max_files": int(os.getenv("PR_MAX_FILES", "") or github.get("max_files", 20)),
    }


def default_repos() -> list[str]:
    """Repos from the PR_REPOS env var (comma separated), else repos.txt."""
    raw = os.getenv("PR_REPOS", "")
    if raw.strip():
        entries = raw.replace("\n", ",").split(",")
    elif REPOS_FILE.exists():
        entries = REPOS_FILE.read_text().splitlines()
    else:
        return []

    return [
        validate_repo(entry)
        for entry in (e.strip() for e in entries)
        if entry and not entry.startswith("#")
    ]
