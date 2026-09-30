"""MCP server that lets GitHub Copilot list and review pull requests.

The tools return raw PR data and diffs; the reviewing is done by the Copilot model
that calls them, so no local LLM is loaded here.
"""

from typing import Annotated

import requests
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .config import ConfigError, default_repos, load_settings, validate_repo
from .github import GitHubFetcher

mcp = MCPServer(
    "pr-reviewer",
    instructions=(
        "Tools for finding pull requests awaiting the user's review and fetching their "
        "diffs. Review the returned diffs yourself; the server does not summarize."
    ),
)


def _fetcher() -> tuple[GitHubFetcher, dict]:
    settings = load_settings()
    fetcher = GitHubFetcher(settings["token"], settings["base_url"], settings["max_files"])
    return fetcher, settings


def _resolve_repos(repos: list[str] | None) -> list[str]:
    selected = [validate_repo(r) for r in repos] if repos else default_repos()
    if not selected:
        raise ConfigError(
            "No repositories given. Pass 'repos' explicitly, set PR_REPOS, or create repos.txt"
        )
    return selected


def _resolve_reviewer(reviewer: str | None, configured_reviewer: str | None) -> str:
    selected = (reviewer or configured_reviewer or "").strip()
    if not selected:
        raise ConfigError(
            "No reviewer given. Pass 'reviewer' explicitly or set GITHUB_REVIEWER/conf.toml"
        )
    return selected


@mcp.tool()
def list_configured_repos() -> dict:
    """List the repositories and reviewer this server is configured to watch."""
    settings = load_settings()
    return {
        "repos": default_repos(),
        "reviewer": settings["reviewer"],
        "base_url": settings["base_url"],
        "days_back": settings["days_back"],
    }


@mcp.tool()
def list_unreviewed_prs(
    repos: Annotated[
        list[str] | None,
        Field(description="owner/repo entries; pass this to select repositories for this question"),
    ] = None,
    days_back: Annotated[
        int | None, Field(description="Only PRs updated in the last N days")
    ] = None,
    reviewer: Annotated[
        str | None,
        Field(description="GitHub login awaiting review; pass this when no configured reviewer exists"),
    ] = None,
) -> dict:
    """List open PRs that request a review from the reviewer and have not been reviewed yet.

    Returns lightweight metadata only. Call get_pr_diff for the code of a specific PR.
    """
    fetcher, settings = _fetcher()
    window = days_back if days_back is not None else settings["days_back"]
    who = _resolve_reviewer(reviewer, settings["reviewer"])

    prs: list[dict] = []
    errors: list[str] = []
    for repo in _resolve_repos(repos):
        try:
            prs.extend(fetcher.search_unreviewed_prs(repo, who, window))
        except requests.RequestException as e:
            errors.append(f"{repo}: {e}")

    return {"reviewer": who, "days_back": window, "count": len(prs), "prs": prs, "errors": errors}


@mcp.tool()
def get_pr_diff(
    repo: Annotated[str, Field(description="Repository in owner/repo form")],
    pr_number: Annotated[int, Field(description="Pull request number")],
) -> dict:
    """Fetch one PR's metadata, description, changed files, and unified diffs for review."""
    fetcher, _ = _fetcher()
    pr = fetcher.fetch_pr(validate_repo(repo), pr_number)
    return dict(pr)


@mcp.tool()
def get_prs_for_review(
    repos: Annotated[
        list[str] | None,
        Field(description="owner/repo entries; pass this to select repositories for this question"),
    ] = None,
    days_back: Annotated[int | None, Field(description="Only PRs updated in the last N days")] = None,
    reviewer: Annotated[
        str | None,
        Field(description="GitHub login awaiting review; pass this when no configured reviewer exists"),
    ] = None,
    limit: Annotated[int, Field(description="Maximum number of PRs to fetch diffs for", ge=1, le=20)] = 5,
) -> dict:
    """List unreviewed PRs and fetch their diffs in one call, ready to be reviewed."""
    fetcher, settings = _fetcher()
    window = days_back if days_back is not None else settings["days_back"]
    who = _resolve_reviewer(reviewer, settings["reviewer"])

    found: list[dict] = []
    errors: list[str] = []
    for repo in _resolve_repos(repos):
        try:
            found.extend(fetcher.search_unreviewed_prs(repo, who, window))
        except requests.RequestException as e:
            errors.append(f"{repo}: {e}")

    detailed = []
    for item in found[:limit]:
        try:
            detailed.append(dict(fetcher.fetch_pr(item["repo"], item["number"])))
        except requests.RequestException as e:
            errors.append(f"{item['repo']}#{item['number']}: {e}")

    return {
        "reviewer": who,
        "days_back": window,
        "total_found": len(found),
        "returned": len(detailed),
        "prs": detailed,
        "errors": errors,
    }


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
