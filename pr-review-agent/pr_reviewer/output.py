import json

from .config import BASE_DIR
from .types import WorkflowState


def format_and_save_results(
    state: WorkflowState, output_config: dict, save: bool = True
) -> WorkflowState:
    """Format, print, and optionally persist workflow results."""
    if state["error"]:
        print(f"\n❌ Error: {state['error']}")
        return state

    output_lines = [
        "",
        "=" * 80,
        f"📊 UNREVIEWED PRs SUMMARY ({len(state['summarized_prs'])} found)",
        "=" * 80,
    ]

    if not state["summarized_prs"]:
        output_lines.append("✓ No unreviewed PRs found!")
    else:
        for i, pr in enumerate(state["summarized_prs"], 1):
            output_lines.extend([
                f"\n[{i}] {pr['repo']}#{pr['number']} - {pr['title']}",
                f"    👤 Author: {pr['author']}",
                f"    🔗 URL: {pr['url']}",
                f"    📅 Updated: {pr['updated_at']}",
            ])
            if pr.get("head_branch") or pr.get("base_branch"):
                output_lines.append(f"    🌿 Branches: {pr.get('head_branch', '')} -> {pr.get('base_branch', '')}")
            if pr.get("changed_files"):
                output_lines.append(
                    f"    📦 Size: {pr['changed_files']} files, +{pr.get('additions', 0)} -{pr.get('deletions', 0)}"
                )
            if pr.get("labels"):
                output_lines.append(f"    🏷️ Labels: {', '.join(pr['labels'])}")
            structured_summary = pr.get("structured_summary")
            if structured_summary:
                output_lines.extend([
                    f"    📝 Overview: {structured_summary['overview']}",
                    "    🔧 Key changes:",
                ])
                output_lines.extend(f"      - {change}" for change in structured_summary["key_changes"])
                output_lines.append("    💡 Suggestions:")
                output_lines.extend(f"      - {suggestion}" for suggestion in structured_summary["suggestions"])
            elif pr.get("summary"):
                output_lines.append(f"    📝 Summary: {pr['summary']}")
            output_lines.append("-" * 80)

    output_text = "\n".join(output_lines)
    print(output_text)
    state["report"] = output_text.strip()

    if not save:
        return state

    # Resolve inside the project dir so results land in the same place regardless of cwd
    output_file = BASE_DIR / str(output_config["json_file"])
    with open(output_file, "w") as f:
        json.dump(state["summarized_prs"], f, indent=2)

    text_output_file = BASE_DIR / str(output_config["text_file"])
    with open(text_output_file, "w") as f:
        f.write(output_text.strip() + "\n")

    print(f"\n✓ Results saved to {output_file} and {text_output_file}")
    return state
