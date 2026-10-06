from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

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

    def _get_paginated_json(
        self,
        path: str,
        params: dict | None = None,
        limit: int | None = None,
    ) -> list:
        results: list = []
        page = 1
        per_page = min(limit or 100, 100)

        while limit is None or len(results) < limit:
            page_params = {**(params or {}), "per_page": per_page, "page": page}
            response = requests.get(
                f"{self.base_url}{path}", headers=self.headers, params=page_params, timeout=30
            )
            response.raise_for_status()
            payload = response.json()
            items = payload.get("items", []) if isinstance(payload, dict) else payload
            if not isinstance(items, list) or not items:
                break

            results.extend(items)
            if limit is not None and len(results) >= limit:
                return results[:limit]
            if 'rel="next"' not in response.headers.get("Link", ""):
                break
            page += 1

        return results

    def _search_prs(self, query: str, open_only: bool = True, limit: int = 100) -> list[dict]:
        result = self._get_json("/search/issues", params={"q": query, "per_page": limit})
        items = result.get("items", []) if isinstance(result, dict) else []
        return [
            self._issue_to_pr_summary(issue)
            for issue in items
            if "pull_request" in issue and (not open_only or issue.get("state") == "open")
        ]

    def _issue_to_pr_summary(self, issue: dict) -> dict:
        return {
            "repo": self._repo_from_issue(issue),
            "number": issue["number"],
            "title": issue["title"],
            "url": issue["html_url"],
            "author": issue["user"]["login"],
            "state": issue.get("state", ""),
            "created_at": issue["created_at"],
            "updated_at": issue["updated_at"],
            "labels": [label["name"] for label in issue.get("labels", [])],
        }

    def _repo_from_issue(self, issue: dict) -> str:
        repository_url = issue.get("repository_url", "")
        return repository_url.rsplit("/repos/", 1)[-1] if "/repos/" in repository_url else ""

    def _is_open_pr(self, issue: dict) -> bool:
        return "pull_request" in issue and issue.get("state") == "open"

    def _compact_user(self, user: dict | None) -> str:
        return (user or {}).get("login", "")

    def _compact_comment(self, item: dict) -> dict:
        return {
            "id": item.get("id"),
            "author": self._compact_user(item.get("user")),
            "body": item.get("body") or "",
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
            "url": item.get("html_url", ""),
        }

    def _compact_review_comment(self, item: dict) -> dict:
        return {
            **self._compact_comment(item),
            "path": item.get("path", ""),
            "line": item.get("line"),
            "original_line": item.get("original_line"),
            "diff_hunk": item.get("diff_hunk", "")[:4000],
            "in_reply_to_id": item.get("in_reply_to_id"),
        }

    def _compact_review(self, item: dict) -> dict:
        return {
            "id": item.get("id"),
            "author": self._compact_user(item.get("user")),
            "state": item.get("state", ""),
            "body": item.get("body") or "",
            "submitted_at": item.get("submitted_at", ""),
            "commit_id": item.get("commit_id", ""),
            "url": item.get("html_url", ""),
        }

    def _parse_time(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                return parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None

    def search_unreviewed_prs(self, repo: str, reviewer: str, days_back: int) -> list[dict]:
        """Search only: cheap listing without per-PR detail or file requests."""
        since_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        query = (
            f"repo:{repo} is:pr is:open updated:>{since_date} "
            f"review-requested:{reviewer} -reviewed-by:{reviewer}"
        )
        return [{**item, "repo": repo} for item in self._search_prs(query)]

    def search_prs_by_author(
        self,
        repo: str,
        author: str,
        days_back: int | None = None,
        state: str = "open",
        limit: int = 100,
    ) -> list[dict]:
        query_parts = [f"repo:{repo}", "is:pr", f"author:{author}"]
        if state != "all":
            query_parts.append(f"is:{state}")
        if days_back is not None:
            since_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            query_parts.append(f"updated:>{since_date}")

        return [
            {**item, "repo": repo}
            for item in self._search_prs(
                " ".join(query_parts), open_only=state == "open", limit=limit
            )
        ]

    def search_prs_by_query(
        self,
        query: str,
        repo: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        query_parts = [query.strip()]
        if repo:
            query_parts.insert(0, f"repo:{repo}")
        if "is:pr" not in query and "type:pr" not in query:
            query_parts.append("is:pr")

        return self._search_prs(" ".join(query_parts), open_only=False, limit=limit)

    def search_stale_review_requests(
        self, repo: str, reviewer: str, days_without_update: int
    ) -> list[dict]:
        stale_before = (datetime.now(timezone.utc) - timedelta(days=days_without_update)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        query = (
            f"repo:{repo} is:pr is:open updated:<{stale_before} "
            f"review-requested:{reviewer} -reviewed-by:{reviewer}"
        )
        return [{**item, "repo": repo} for item in self._search_prs(query)]

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

    def fetch_pr_comments(self, repo: str, number: int, limit: int = 100) -> dict:
        issue_comments = self._get_paginated_json(
            f"/repos/{repo}/issues/{number}/comments", limit=limit
        )
        review_comments = self._get_paginated_json(
            f"/repos/{repo}/pulls/{number}/comments", limit=limit
        )
        reviews = self._get_paginated_json(f"/repos/{repo}/pulls/{number}/reviews", limit=limit)

        return {
            "repo": repo,
            "number": number,
            "issue_comments": [self._compact_comment(item) for item in issue_comments],
            "review_comments": [self._compact_review_comment(item) for item in review_comments],
            "reviews": [self._compact_review(item) for item in reviews],
        }

    def fetch_pr_review_state(self, repo: str, number: int) -> dict:
        details = self._fetch_pr_details(repo, number)
        reviews = [
            self._compact_review(item)
            for item in self._get_paginated_json(f"/repos/{repo}/pulls/{number}/reviews")
        ]
        latest_by_user: dict[str, dict] = {}
        for review in reviews:
            author = review["author"]
            submitted_at = self._parse_time(review.get("submitted_at"))
            previous = latest_by_user.get(author)
            previous_at = self._parse_time(previous.get("submitted_at")) if previous else None
            if author and (previous is None or (submitted_at and previous_at and submitted_at >= previous_at)):
                latest_by_user[author] = review

        latest_reviews = list(latest_by_user.values())
        requested_reviewers = [
            self._compact_user(item) for item in details.get("requested_reviewers", [])
        ]
        requested_teams = [item.get("slug", "") for item in details.get("requested_teams", [])]

        return {
            "repo": repo,
            "number": number,
            "state": details.get("state", ""),
            "draft": details.get("draft", False),
            "mergeable": details.get("mergeable"),
            "requested_reviewers": requested_reviewers,
            "requested_teams": requested_teams,
            "latest_reviews": latest_reviews,
            "approved_by": [item["author"] for item in latest_reviews if item.get("state") == "APPROVED"],
            "changes_requested_by": [
                item["author"] for item in latest_reviews if item.get("state") == "CHANGES_REQUESTED"
            ],
            "commented_by": [item["author"] for item in latest_reviews if item.get("state") == "COMMENTED"],
        }

    def fetch_pr_checks(self, repo: str, number: int) -> dict:
        details = self._fetch_pr_details(repo, number)
        head = details.get("head") or {}
        sha = head.get("sha", "")
        status = self._get_json(f"/repos/{repo}/commits/{sha}/status") if sha else {}
        check_runs_payload = (
            self._get_json(f"/repos/{repo}/commits/{sha}/check-runs", params={"per_page": 100})
            if sha
            else {}
        )
        check_runs = (
            check_runs_payload.get("check_runs", []) if isinstance(check_runs_payload, dict) else []
        )

        return {
            "repo": repo,
            "number": number,
            "head_sha": sha,
            "combined_status": {
                "state": status.get("state") if isinstance(status, dict) else None,
                "total_count": status.get("total_count") if isinstance(status, dict) else 0,
                "statuses": [
                    {
                        "context": item.get("context", ""),
                        "state": item.get("state", ""),
                        "description": item.get("description", ""),
                        "target_url": item.get("target_url", ""),
                    }
                    for item in (status.get("statuses", []) if isinstance(status, dict) else [])
                ],
            },
            "check_runs": [
                {
                    "name": item.get("name", ""),
                    "status": item.get("status", ""),
                    "conclusion": item.get("conclusion"),
                    "started_at": item.get("started_at", ""),
                    "completed_at": item.get("completed_at", ""),
                    "url": item.get("html_url", ""),
                }
                for item in check_runs
            ],
        }

    def fetch_pr_timeline(self, repo: str, number: int, limit: int = 100) -> dict:
        events = self._get_paginated_json(f"/repos/{repo}/issues/{number}/timeline", limit=limit)
        return {
            "repo": repo,
            "number": number,
            "events": [self._compact_timeline_event(item) for item in events],
        }

    def fetch_prs_with_changes_after_review(
        self, repo: str, reviewer: str, days_back: int
    ) -> list[dict]:
        since_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        query = f"repo:{repo} is:pr is:open updated:>{since_date} reviewed-by:{reviewer}"
        changed_after_review: list[dict] = []

        for pr in self._search_prs(query):
            reviews = [
                self._compact_review(item)
                for item in self._get_paginated_json(f"/repos/{repo}/pulls/{pr['number']}/reviews")
            ]
            reviewer_reviews = [item for item in reviews if item.get("author") == reviewer]
            latest_review = self._latest_review(reviewer_reviews)
            latest_review_at = self._parse_time(latest_review.get("submitted_at")) if latest_review else None
            latest_commit = self._latest_pr_commit(repo, pr["number"])
            latest_commit_at = self._parse_time(latest_commit.get("committed_at"))

            if latest_review and latest_review_at and latest_commit_at and latest_commit_at > latest_review_at:
                changed_after_review.append(
                    {
                        **pr,
                        "repo": repo,
                        "reviewer": reviewer,
                        "latest_review": latest_review,
                        "latest_commit": latest_commit,
                    }
                )

        return changed_after_review

    def _compact_timeline_event(self, item: dict) -> dict:
        actor = item.get("actor") or item.get("user")
        return {
            "id": item.get("id"),
            "event": item.get("event", ""),
            "actor": self._compact_user(actor),
            "created_at": item.get("created_at", ""),
            "commit_id": item.get("commit_id", ""),
            "body": item.get("body") or "",
            "state": item.get("state", ""),
            "url": item.get("html_url") or item.get("url", ""),
        }

    def _latest_review(self, reviews: list[dict]) -> dict | None:
        return max(
            reviews,
            key=lambda item: self._parse_time(item.get("submitted_at")) or datetime.min.replace(
                tzinfo=timezone.utc
            ),
            default=None,
        )

    def _latest_pr_commit(self, repo: str, number: int) -> dict:
        commits = self._get_paginated_json(f"/repos/{repo}/pulls/{number}/commits")
        latest = max(
            commits,
            key=lambda item: self._parse_time(
                ((item.get("commit") or {}).get("committer") or {}).get("date")
            )
            or datetime.min.replace(tzinfo=timezone.utc),
            default={},
        )
        commit = latest.get("commit") or {}
        committer = commit.get("committer") or {}
        author = commit.get("author") or {}
        return {
            "sha": latest.get("sha", ""),
            "message": commit.get("message", ""),
            "committed_at": committer.get("date", ""),
            "author": author.get("name", ""),
            "url": latest.get("html_url", ""),
        }

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
