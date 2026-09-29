from typing import TypedDict


class PRInfo(TypedDict):
    number: int
    title: str
    url: str
    repo: str
    body: str
    author: str
    created_at: str
    updated_at: str
    base_branch: str
    head_branch: str
    changed_files: int
    additions: int
    deletions: int
    labels: list[str]
    files: list[dict]


class WorkflowState(TypedDict):
    repos: list[str]
    git_token: str
    prs: list[PRInfo]
    summarized_prs: list[dict]
    error: str | None
    report: str
