from datetime import datetime, timedelta

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
        response = requests.get(f"{self.base_url}{path}", headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def fetch_unreviewed_prs(self, repo: str, reviewer: str, days_back: int) -> list[PRInfo]:
        """Fetch open PRs requested for reviewer, not reviewed, updated in last N days."""
        try:
            since_date = (datetime.utcnow() - timedelta(days=days_back)).isoformat()

            query = (
                f"repo:{repo} is:pr is:open updated:>{since_date} "
                f"review-requested:{reviewer} -reviewed-by:{reviewer}"
            )
            search_url = f"{self.base_url}/search/issues"
            params = {"q": query, "per_page": 100}

            response = requests.get(search_url, headers=self.headers, params=params)
            response.raise_for_status()
            issues = response.json().get("items", [])

            prs = []
            for issue in issues:
                if "pull_request" in issue and issue.get("state") == "open":
                    details = self._fetch_pr_details(repo, issue["number"])
                    files = self._fetch_pr_files(repo, issue["number"])
                    prs.append(PRInfo(
                        number=issue["number"],
                        title=issue["title"],
                        url=issue["html_url"],
                        repo=repo,
                        body=details.get("body") or issue.get("body", ""),
                        author=issue["user"]["login"],
                        created_at=issue["created_at"],
                        updated_at=issue["updated_at"],
                        base_branch=details.get("base", {}).get("ref", ""),
                        head_branch=details.get("head", {}).get("ref", ""),
                        changed_files=details.get("changed_files", 0),
                        additions=details.get("additions", 0),
                        deletions=details.get("deletions", 0),
                        labels=[label["name"] for label in issue.get("labels", [])],
                        files=files,
                    ))

            print(f"✓ Found {len(prs)} unreviewed PRs in {repo}")
            return prs

        except requests.exceptions.RequestException as e:
            print(f"✗ Error fetching PRs from {repo}: {e}")
            return []

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
                # GitHub omits "patch" for binary/huge files; truncate to keep LLM context small
                "patch": (item.get("patch") or "")[:2000],
            }
            for item in files[:self.max_files]
        ]
