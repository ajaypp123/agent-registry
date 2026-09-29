import re

from .types import PRInfo


EMPTY_SUMMARY = {
    "overview": "",
    "key_changes": [],
    "suggestions": [],
}


def build_structured_summary(pr: PRInfo, llm_output: str) -> dict:
    """Convert model output and PR metadata into a clean structured summary."""
    parsed = _parse_sectioned_summary(llm_output)
    if parsed:
        return _normalize_summary(parsed, pr)

    return _fallback_summary(pr, llm_output)


def error_summary(message: str) -> dict:
    summary = EMPTY_SUMMARY.copy()
    summary["overview"] = f"Summary generation failed: {message}"
    summary["suggestions"] = ["Review this PR manually because automated summary generation failed."]
    return summary


def format_pr_context(pr: PRInfo) -> str:
    """Create compact PR context for the LLM prompt."""
    lines = [
        f"Title: {pr['title']}",
        f"Author: {pr['author']}",
        f"Repository: {pr['repo']}",
        f"Branches: {pr.get('head_branch', '')} -> {pr.get('base_branch', '')}",
        f"Size: {pr.get('changed_files', 0)} files, +{pr.get('additions', 0)} -{pr.get('deletions', 0)}",
    ]

    labels = pr.get("labels", [])
    if labels:
        lines.append(f"Labels: {', '.join(labels)}")

    body = _one_line(pr.get("body", ""))
    if body:
        lines.append(f"Description: {body[:1200]}")

    files = pr.get("files", []) or []
    if files:
        lines.append("Changed files:")
        for item in files[:15]:
            lines.append(
                f"- {item.get('filename', '')} ({item.get('status', '')}, "
                f"+{item.get('additions', 0)} -{item.get('deletions', 0)})"
            )

    # Include the actual diffs so the LLM can review real code, not just metadata
    diff_budget = 6000
    diff_lines = []
    for item in files:
        patch = item.get("patch", "")
        if not patch:
            continue
        entry = f"--- {item.get('filename', '')} ---\n{patch}"
        if diff_budget - len(entry) < 0:
            break
        diff_lines.append(entry)
        diff_budget -= len(entry)

    if diff_lines:
        lines.append("\nCode diffs:")
        lines.extend(diff_lines)

    return "\n".join(lines)


_SECTION_HEADERS = ("overview", "key changes", "suggestions")


def _parse_sectioned_summary(text: str) -> dict | None:
    """Parse the model's plain-text 'Overview / Key Changes / Suggestions' response."""
    cleaned = _strip_code_fence(_strip_prompt_echo(text))
    if not cleaned:
        return None

    header_pattern = re.compile(
        r"^\s*(overview|key changes|suggestions)\s*:\s*", flags=re.IGNORECASE | re.MULTILINE
    )
    matches = list(header_pattern.finditer(cleaned))
    if not matches:
        return None

    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
        key = match.group(1).lower()
        sections[key] = cleaned[start:end].strip()

    if not sections:
        return None

    return {
        "overview": sections.get("overview", ""),
        "key_changes": sections.get("key changes", ""),
        "suggestions": sections.get("suggestions", ""),
    }


def _normalize_summary(parsed: dict, pr: PRInfo) -> dict:
    summary = EMPTY_SUMMARY.copy()
    summary["overview"] = _clean_text(parsed.get("overview")) or _title_overview(pr)
    summary["key_changes"] = _as_list(parsed.get("key_changes")) or _file_change_bullets(pr)
    summary["suggestions"] = _as_list(parsed.get("suggestions")) or _default_concerns(pr)
    return summary


def _fallback_summary(pr: PRInfo, llm_output: str) -> dict:
    body = pr.get("body", "") or ""
    cleaned_output = _clean_text(_strip_prompt_echo(llm_output))
    package_update = _extract_renovate_update(body) or _extract_renovate_update(cleaned_output)
    summary = EMPTY_SUMMARY.copy()

    if package_update:
        package_name, update_type, old_version, new_version = package_update
        summary["overview"] = f"Renovate proposes a {update_type} update for {package_name}."
        summary["key_changes"] = [f"Updates {package_name} from {old_version} to {new_version}."]
        summary["suggestions"] = [
            "Check compatibility with the build and runtime environment.",
            "Verify CI passes before merging because automerge is disabled.",
        ]
        return summary

    summary["overview"] = _first_sentence(cleaned_output) or _body_overview(pr) or _title_overview(pr)
    summary["key_changes"] = _file_change_bullets(pr) or [_title_overview(pr)]
    summary["suggestions"] = _default_concerns(pr)
    return summary


def _extract_renovate_update(body: str) -> tuple[str, str, str, str] | None:
    row_pattern = re.compile(
        r"\|\s*(?P<package>[^|]+?)\s*\|\s*[^|]+\s*\|\s*(?P<update>[^|]+?)\s*\|\s*`(?P<old>[^`]+)`\s*->\s*`(?P<new>[^`]+)`\s*\|"
    )
    for match in row_pattern.finditer(body):
        package_name = match.group("package").strip()
        if package_name.lower() == "package":
            continue
        return (
            package_name,
            match.group("update").strip(),
            match.group("old").strip(),
            match.group("new").strip(),
        )
    return None


def _strip_prompt_echo(text: str) -> str:
    if not text:
        return ""
    marker = "Review:"
    if marker in text:
        text = text.split(marker, 1)[1]
    return text.strip()


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    fence_match = re.match(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return fence_match.group(1).strip() if fence_match else text


def _clean_text(value: object) -> str:
    text = _strip_code_fence(_one_line(value))
    if _looks_like_broken_json(text) or _is_low_signal_text(text):
        return ""
    return text


def _looks_like_broken_json(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return stripped.startswith("{") or stripped.startswith("[")


def _is_low_signal_text(text: str) -> bool:
    normalized = text.strip().lower().rstrip(":")
    if normalized in {
        "this pr contains the following updates",
        "review requested for this pr",
    }:
        return True
    return "generated by [renovate bot]" in normalized


def _title_overview(pr: PRInfo) -> str:
    return _clean_title(pr["title"])


def _body_overview(pr: PRInfo) -> str:
    body = pr.get("body", "") or ""
    for line in body.splitlines():
        line = _clean_text(line)
        if line and not line.startswith("|") and not line.startswith("---") and not line.startswith("<!--"):
            return line[:220]
    return ""


def _clean_title(title: str) -> str:
    title = _one_line(title)
    title = re.sub(r"^[A-Z]+-\d+\s*:?\s*", "", title)
    return title


def _file_change_bullets(pr: PRInfo) -> list[str]:
    files = pr.get("files", []) or []
    bullets = []
    changed_files = pr.get("changed_files", 0)
    additions = pr.get("additions", 0)
    deletions = pr.get("deletions", 0)

    if changed_files:
        bullets.append(f"Changes {changed_files} file(s) with +{additions}/-{deletions} lines.")

    for item in files[:5]:
        filename = item.get("filename", "")
        if not filename:
            continue
        status = item.get("status", "modified")
        changes = item.get("changes", 0)
        bullets.append(f"{status.title()} {filename} ({changes} line changes).")

    return bullets


def _default_concerns(pr: PRInfo) -> list[str]:
    concerns = ["Review the diff, tests, and CI status before approving."]
    files = pr.get("files", []) or []
    filenames = [item.get("filename", "") for item in files]

    if any("secret" in filename.lower() or "config" in filename.lower() for filename in filenames):
        concerns.append("Pay extra attention to configuration and secret-handling changes.")
    if pr.get("changed_files", 0) > len(files) and files:
        concerns.append("Only the first changed files were included in this summary; inspect the full PR for remaining files.")

    return concerns


def _first_sentence(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    match = re.match(r"(.+?[.!?])(?:\s|$)", cleaned)
    return match.group(1) if match else cleaned[:220]


def _one_line(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [cleaned for item in value if (cleaned := _clean_text(item))]
    if isinstance(value, str) and value.strip():
        bullets = [re.sub(r"^[-*]\s*", "", line).strip() for line in value.splitlines()]
        return [cleaned for bullet in bullets if (cleaned := _clean_text(bullet))]
    return []
