"""FastAPI web service for the PR Reviewer agent."""

import os
import traceback
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pr_reviewer.config import CONFIG_FILE, config_template_text, load_config
from pr_reviewer.service import parse_repos, read_repos_file, run_review

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="PR Reviewer Agent", version="1.0.0")


class ReviewRequest(BaseModel):
    config_text: str = Field(default="", description="TOML config used when conf.toml is absent")
    repos_text: str = Field(default="", description="One owner/repo per line")
    git_token: str = Field(default="", description="GitHub token; falls back to GIT_TOKEN env")


class ReviewResponse(BaseModel):
    error: str | None = None
    report: str = ""
    repos: list[str] = []
    prs: list[dict] = []


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/defaults")
def defaults() -> dict:
    """Initial values for the GUI: conf.toml if present, otherwise the template pretext."""
    config_present = CONFIG_FILE.exists() and CONFIG_FILE.stat().st_size > 0
    try:
        repos = read_repos_file(load_config(config_template_text()))
    except Exception:
        repos = []

    return {
        "config_text": config_template_text(),
        "config_from_file": config_present,
        "repos_text": "\n".join(repos),
        "token_from_env": bool(os.getenv("GIT_TOKEN")),
    }


@app.post("/api/review", response_model=ReviewResponse)
def review(request: ReviewRequest) -> ReviewResponse:
    try:
        repos = parse_repos(request.repos_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    token = request.git_token.strip() or os.getenv("GIT_TOKEN", "")
    if not token:
        raise HTTPException(
            status_code=400,
            detail="No GitHub token supplied and GIT_TOKEN is not set",
        )

    try:
        state = run_review(
            config_text=request.config_text,
            repos=repos or None,
            git_token=token,
            save_output=False,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Review failed: {e}") from e

    return ReviewResponse(
        error=state.get("error"),
        report=state.get("report", ""),
        repos=state.get("repos", []),
        prs=state.get("summarized_prs", []),
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
