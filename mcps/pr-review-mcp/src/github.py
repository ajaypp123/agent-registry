from datetime import datetime, timedelta, timezone

import requests

from .types import PRInfo


class GitHubFetcher:
    def __init__(self, token: str, base_url: str, max_files: int = 20):
        self.token = token
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        self.base_url = base_url.rstrip("/")
        self.max_files = max_files

    def _get_json(self, path: str, params: dict | None = None) -> dict | list:
        response = requests.get(
            f"{self.base_url}{path}", headers=self.headers, params=params, timeout=30
        )
        response.raise_for_status()
        return response.json()

    def search_unreviewed_prs(self, repo: str, reviewer: str, days_back: int) -> list[dict]:
        """Search only: cheap listing without per-PR detail or file requests."""
        since_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        query = (
            f"repo:{repo} is:pr is:open updated:>{since_date} "
            f"review-requested:{reviewer} -reviewed-by:{reviewer}"
        )
        result = self._get_json("/search/issues", params={"q": query, "per_page": 100})
        items = result.get("items", []) if isinstance(result, dict) else []

        return [
            {
                "repo": repo,
                "number": issue["number"],
                "title": issue["title"],
                "url": issue["html_url"],
                "author": issue["user"]["login"],
                "created_at": issue["created_at"],
                "updated_at": issue["updated_at"],
                "labels": [label["name"] for label in issue.get("labels", [])],
            }
            for issue in items
            if "pull_request" in issue and issue.get("state") == "open"
        ]

    def fetch_pr(self, repo: str, number: int) -> PRInfo:
        """Full PR payload including file list and diffs."""
        details = self._fetch_pr_details(repo, number)
        files = self._fetch_pr_files(repo, number)
        user = details.get("user") or {}

        return PRInfo(
            number=number,
            title=details.get("title", ""),
            url=details.get("html_url", ""),
            repo=repo,
            body=details.get("body") or "",
            author=user.get("login", ""),
            created_at=details.get("created_at", ""),
            updated_at=details.get("updated_at", ""),
            base_branch=details.get("base", {}).get("ref", ""),
            head_branch=details.get("head", {}).get("ref", ""),
            changed_files=details.get("changed_files", 0),
            additions=details.get("additions", 0),
            deletions=details.get("deletions", 0),
            labels=[label["name"] for label in details.get("labels", [])],
            files=files,
        )

    def fetch_unreviewed_prs(self, repo: str, reviewer: str, days_back: int) -> list[PRInfo]:
        """Fetch open PRs requested for reviewer, not reviewed, updated in last N days."""
        return [
            self.fetch_pr(repo, issue["number"])
            for issue in self.search_unreviewed_prs(repo, reviewer, days_back)
        ]

    def _fetch_pr_details(self, repo: str, number: int) -> dict:
        details = self._get_json(f"/repos/{repo}/pulls/{number}")
        return details if isinstance(details, dict) else {}

    def _fetch_pr_files(self, repo: str, number: int) -> list[dict]:
        files = self._get_json(
            f"/repos/{repo}/pulls/{number}/files",
            params={"per_page": self.max_files},
        )
        if not isinstance(files, list):
            return []

        return [
            {
                "filename": item.get("filename", ""),
                "status": item.get("status", ""),
                "additions": item.get("additions", 0),
                "deletions": item.get("deletions", 0),
                "changes": item.get("changes", 0),
                # GitHub omits "patch" for binary/huge files
                "patch": (item.get("patch") or "")[:8000],
            }
            for item in files[:self.max_files]
        ]
