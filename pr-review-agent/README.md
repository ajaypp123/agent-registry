
# GitHub PR Reviewer using LangChain + LangGraph

Fetches PRs from configured repositories that have not been reviewed by the configured reviewer, then either lists them or summarizes them with a local HuggingFace model.

## Setup

### 1. Install Dependencies

---
```bash
pip install -r requirements.txt
```
---

### 2. Set Environment Variables

---
```bash
export GIT_TOKEN="your_github_personal_access_token"
```
---

The token needs access to read the configured repositories.

### 3. Configure Repositories

Edit `repos.txt` with one repository per line:

---
```text
owner/repo1
owner/repo2
owner/repo3
```
---

### 4. Configure Runtime Options

Edit `conf.toml`:

---
```toml
[github]
# For GitHub Enterprise use https://<your-host>/api/v3
base_url = "https://api.github.com"
reviewer = "your-github-username"
days_back = 7

[workflow]
# Options: "summaries" or "fetch_only"
mode = "summaries"
repos_file = "repos.txt"

[output]
json_file = "pr_summaries.json"
text_file = "pr_summaries.txt"

[llm]
model_id = "codellama/CodeLlama-7b-hf"
task = "text-generation"
```
---

Use `mode = "fetch_only"` to skip LLM initialization and only list fetched PRs.

### 5. Run Program

---
```bash
python3 pr_review.py
```
---

### 6. Run as a Web Service

---
```bash
uvicorn server:app --host 127.0.0.1 --port 8000
```
---

Open http://127.0.0.1:8000 for the GUI. It provides:

- A TOML configuration editor, prefilled with `conf.toml` when present, otherwise with `conf.toml.template` as pretext. The server always prefers `conf.toml`; the submitted text is used only when that file is missing.
- A repository list box (same format as `repos.txt`, one `owner/repo` per line).
- An optional GitHub token field that falls back to the `GIT_TOKEN` environment variable.
- Rendered PR cards with metadata, overview, key changes, suggestions, and changed files.

Endpoints:

---
```text
GET  /health         liveness probe
GET  /api/defaults   config pretext, repo list, whether GIT_TOKEN is set
POST /api/review     {config_text, repos_text, git_token} -> {report, repos, prs}
```
---

The web service keeps results in memory and does not write `pr_summaries.*`. Bind to `127.0.0.1` unless an authenticating reverse proxy is in front of it, since the endpoints are unauthenticated and accept a GitHub token.

## Package Layout

---
```text
pr_review.py              # CLI entrypoint
server.py                 # FastAPI web service
static/                   # GUI (index.html, app.css, app.js)
pr_reviewer/
  config.py               # conf.toml loading/defaults/validation
  github.py               # GitHub search API client
  llm.py                  # LangChain summarization chain
  output.py               # console, JSON, and text output
  service.py              # shared run_review() used by CLI and web service
  types.py                # shared TypedDict definitions
  workflow.py             # LangGraph workflow
```
---

## Output

- Console: formatted list of PRs with optional summaries
- `pr_summaries.json`: structured result data
- `pr_summaries.txt`: same clean report printed to the console

## Example Output

---
```text
[1] owner/repo1#42 - Add new feature
    👤 Author: contributor
    🔗 URL: https://github.com/...
    📅 Updated: 2026-09-23T16:00:00Z
    📝 Summary: This PR adds a new authentication method...
```
---

## Performance Notes

- `summaries` mode initializes the configured HuggingFace model.
- `fetch_only` mode does not initialize the LLM.
- Large local models may need significant RAM and disk cache.

## Troubleshooting

**Module not found:**

---
```bash
pip install -r requirements.txt
```
---

**GIT_TOKEN not working:**

- Check that the token has access to the configured repositories.
- Verify the token is active and exported in the shell running the script.


# HuggingFace

```
# Disk usage, including model and auxiliary caches
du -h -d 1 ~/.cache/huggingface

# List cached repositories, largest first
hf cache ls --sort size:desc

# Include individual model revisions
hf cache ls --revisions

# Preview deletion
hf cache rm model/ORG/MODEL --dry-run

# Delete after reviewing the preview
hf cache rm model/ORG/MODEL

# Review what would be removed
hf cache prune --dry-run

# Remove after review
hf cache prune

# Preview deletion
hf cache rm model/codellama/CodeLlama-7b-hf --dry-run

# Delete the cached model (asks for confirmation)
hf cache rm model/codellama/CodeLlama-7b-hf

# Confirm the remaining models
hf cache ls
```

