import os
import re

from langchain_core.runnables import Runnable
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from .config import BASE_DIR, load_config
from .github import GitHubFetcher
from .llm import build_summary_chain
from .output import format_and_save_results
from .summary import build_structured_summary, error_summary, format_pr_context
from .types import WorkflowState


class PRReviewerGraph:
    def __init__(
        self,
        config: dict | None = None,
        git_token: str | None = None,
        repos: list[str] | None = None,
        save_output: bool = True,
    ):
        self.config = config or load_config()
        self.git_token = git_token or os.getenv("GIT_TOKEN", "")
        self.repos = repos
        self.save_output = save_output
        self.github = GitHubFetcher(
            self.git_token,
            self.config["github"]["base_url"],
            int(self.config["github"].get("max_files", 20)),
        )
        self.llm_chain: Runnable | None = None

        if self.config["workflow"]["mode"] == "summaries":
            print("⏳ Initializing LLM...")
            self.llm_chain = build_summary_chain(
                self.config["llm"]["model_id"],
                self.config["llm"]["task"],
            )

    def load_repos(self, state: WorkflowState) -> WorkflowState:
        """Node: Load repositories from the caller-supplied list or from the repos file."""
        print("\n📂 Loading repositories...")

        if self.repos is not None:
            repos = [repo.strip() for repo in self.repos if repo.strip()]
        else:
            repos_file = BASE_DIR / self.config["workflow"]["repos_file"]
            if not os.path.exists(repos_file):
                state["error"] = f"{repos_file} not found. Create it with repo names (owner/repo format)"
                return state

            with open(repos_file, "r") as f:
                repos = [line.strip() for line in f if line.strip() and not line.startswith("#")]

        if not repos:
            state["error"] = "No repositories provided"
            return state

        state["repos"] = repos
        state["git_token"] = self.git_token

        if not state["git_token"]:
            state["error"] = "GitHub token not provided and GIT_TOKEN environment variable not set"
            return state

        print(f"✓ Loaded {len(repos)} repositories")
        return state

    def fetch_prs(self, state: WorkflowState) -> WorkflowState:
        """Node: Fetch unreviewed PRs from all repos."""
        if state["error"]:
            return state

        print("\n🔍 Fetching unreviewed PRs...")
        all_prs = []
        reviewer = self.config["github"]["reviewer"]
        days_back = int(self.config["github"]["days_back"])

        for repo in state["repos"]:
            prs = self.github.fetch_unreviewed_prs(repo, reviewer, days_back)
            all_prs.extend(prs)

        state["prs"] = all_prs
        print(f"✓ Total PRs found: {len(all_prs)}")
        return state

    def summarize_prs(self, state: WorkflowState) -> WorkflowState:
        """Node: Summarize each PR using LLM."""
        if state["error"] or not state["prs"]:
            return state

        if self.config["workflow"]["mode"] == "fetch_only":
            state["summarized_prs"] = [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "url": pr["url"],
                    "repo": pr["repo"],
                    "author": pr["author"],
                    "updated_at": pr["updated_at"],
                    "base_branch": pr.get("base_branch", ""),
                    "head_branch": pr.get("head_branch", ""),
                    "changed_files": pr.get("changed_files", 0),
                    "additions": pr.get("additions", 0),
                    "deletions": pr.get("deletions", 0),
                    "labels": pr.get("labels", []),
                    "files": pr.get("files", []),
                    "structured_summary": build_structured_summary(pr, ""),
                }
                for pr in state["prs"]
            ]
            return state

        print("\n📝 Summarizing PRs with LLM...")
        summarized = []

        for i, pr in enumerate(state["prs"], 1):
            try:
                print(f"  [{i}/{len(state['prs'])}] Summarizing {pr['repo']}#{pr['number']}...")
                if self.llm_chain is None:
                    raise RuntimeError("LLM chain is not initialized")

                summary = self.llm_chain.invoke({
                    "context": format_pr_context(pr),
                })
                summary = re.sub(r"\s+", " ", summary.strip())
                print(f"    ↳ raw LLM output: {summary[:300]}")
                structured_summary = build_structured_summary(pr, summary)

                summarized.append({
                    "number": pr["number"],
                    "title": pr["title"],
                    "url": pr["url"],
                    "repo": pr["repo"],
                    "author": pr["author"],
                    "updated_at": pr["updated_at"],
                    "base_branch": pr.get("base_branch", ""),
                    "head_branch": pr.get("head_branch", ""),
                    "changed_files": pr.get("changed_files", 0),
                    "additions": pr.get("additions", 0),
                    "deletions": pr.get("deletions", 0),
                    "labels": pr.get("labels", []),
                    "files": pr.get("files", []),
                    "summary": structured_summary["overview"],
                    "structured_summary": structured_summary,
                })

            except Exception as e:
                print(f"  ✗ Error summarizing PR: {e}")
                summarized.append({
                    "number": pr["number"],
                    "title": pr["title"],
                    "url": pr["url"],
                    "repo": pr["repo"],
                    "author": pr["author"],
                    "updated_at": pr["updated_at"],
                    "base_branch": pr.get("base_branch", ""),
                    "head_branch": pr.get("head_branch", ""),
                    "changed_files": pr.get("changed_files", 0),
                    "additions": pr.get("additions", 0),
                    "deletions": pr.get("deletions", 0),
                    "labels": pr.get("labels", []),
                    "files": pr.get("files", []),
                    "summary": f"Error: {str(e)}",
                    "structured_summary": error_summary(str(e)),
                })

        state["summarized_prs"] = summarized
        return state

    def format_output(self, state: WorkflowState) -> WorkflowState:
        """Node: Format and display results."""
        return format_and_save_results(state, self.config["output"], save=self.save_output)

    def build_graph(self) -> CompiledStateGraph:
        """Build LangGraph workflow."""
        graph = StateGraph(WorkflowState)

        graph.add_node("load_repos", self.load_repos)
        graph.add_node("fetch_prs", self.fetch_prs)
        graph.add_node("summarize_prs", self.summarize_prs)
        graph.add_node("format_output", self.format_output)

        graph.add_edge("load_repos", "fetch_prs")
        graph.add_edge("fetch_prs", "summarize_prs")
        graph.add_edge("summarize_prs", "format_output")

        graph.set_entry_point("load_repos")

        return graph.compile()
