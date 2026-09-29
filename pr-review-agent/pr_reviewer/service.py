"""Shared entry point for running the PR review workflow (CLI and web service)."""

import os
import re
import threading

from .config import BASE_DIR, load_config
from .types import WorkflowState
from .workflow import PRReviewerGraph

REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")

# The HuggingFace pipeline is not safe to call concurrently, so serialize runs.
_run_lock = threading.Lock()


def initial_state() -> WorkflowState:
    return {
        "repos": [],
        "git_token": "",
        "prs": [],
        "summarized_prs": [],
        "error": None,
        "report": "",
    }


def parse_repos(text: str) -> list[str]:
    """Parse a repos.txt-style block into a validated list of owner/repo entries."""
    repos = []
    for line in text.splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        if not REPO_PATTERN.match(entry):
            raise ValueError(f"Invalid repository name {entry!r}; expected owner/repo")
        repos.append(entry)
    return repos


def read_repos_file(config: dict) -> list[str]:
    repos_file = BASE_DIR / str(config["workflow"]["repos_file"])
    if not repos_file.exists():
        return []
    return parse_repos(repos_file.read_text())


def run_review(
    config_text: str | None = None,
    repos: list[str] | None = None,
    git_token: str | None = None,
    save_output: bool = True,
) -> WorkflowState:
    """Run the full workflow and return the final state."""
    config = load_config(config_text)
    token = git_token or os.getenv("GIT_TOKEN", "")

    if repos is not None:
        for repo in repos:
            if not REPO_PATTERN.match(repo):
                raise ValueError(f"Invalid repository name {repo!r}; expected owner/repo")

    with _run_lock:
        reviewer = PRReviewerGraph(
            config=config,
            git_token=token,
            repos=repos,
            save_output=save_output,
        )
        return reviewer.build_graph().invoke(initial_state())
