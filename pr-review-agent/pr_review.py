#!/usr/bin/env python3
"""
LangChain + LangGraph PR Reviewer
Fetches unreviewed PRs from multiple repos and summarizes them using local LLM.
"""

from dotenv import load_dotenv

from pr_reviewer.service import run_review


def main():
    load_dotenv()
    print("\n🚀 LangChain PR Reviewer - Starting...\n")

    try:
        run_review()
        print("\n✅ Workflow completed successfully!")
    except Exception as e:
        print(f"\n❌ Workflow failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
