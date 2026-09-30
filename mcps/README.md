
# PR Review MCP

## Run the MCP Server with Docker

The MCP server uses **stdio** transport, so it is intended to be launched by an MCP client such as GitHub Copilot. It does not expose an HTTP port. The container only includes the MCP dependencies; it does not install or start the local HuggingFace LLM used by the separate CLI and web app. The connected LLM reviews the PR data returned by the MCP tools.

From this directory, build the image:

```sh
sh build-docker.sh
```

To use a different image tag, pass it as the first argument, for example `sh build-docker.sh my-pr-reviewer-mcp:dev`.

Configure the MCP client to launch Docker with interactive stdin. For VS Code, add an entry like this to `.vscode/mcp.json` (merge it into the existing `servers` object):

```json
{
  "servers": {
    "pr-reviewer-docker": {
      "type": "stdio",
      "command": "docker",
      "args": [
        "run", "--rm", "-i",
        "--env", "GIT_TOKEN",
        "--env", "GITHUB_REVIEWER",
        "--env", "GITHUB_BASE_URL",
        "--env", "PR_REPOS",
        "pr-reviewer-mcp:latest"
      ],
      "env": {
        "GIT_TOKEN": "${input:github-token}",
        "GITHUB_REVIEWER": "${input:github-reviewer}",
        "PR_REPOS": "${input:pr-repos}"
      }
    }
  },
  "inputs": [
    {
      "type": "promptString",
      "id": "github-token",
      "description": "GitHub token with read access to the repositories",
      "password": true
    },
    {
      "type": "promptString",
      "id": "github-reviewer",
      "description": "GitHub username whose requested reviews to find"
    },
    {
      "type": "promptString",
      "id": "pr-repos",
      "description": "Comma-separated repositories, for example owner/repo"
    }
  ]
}
```

The `GIT_TOKEN` is passed at runtime and is not included in the image. `PR_REPOS` accepts comma-separated `owner/repo` values. Instead of environment variables, you can mount `conf.toml` and `repos.txt` into `/app` as read-only files; never add the token to either file or the Docker image. Rebuild the image after changing the MCP code or dependencies.

### Example question for the connected LLM

> Find the pull requests awaiting review for the configured repositories that were updated in the last 7 days. For each PR, inspect its diff and review it for correctness, regressions, security issues, and missing tests. Report only actionable findings, with severity, file and line where possible, and a short rationale. If you find no issues, say so and mention any testing limitations. Do not modify files.

The LLM can use `list_unreviewed_prs` to discover PRs, `get_pr_diff` to inspect one PR, or `get_prs_for_review` to fetch a limited number of PRs and diffs together.
```
---
