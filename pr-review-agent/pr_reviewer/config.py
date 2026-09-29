import importlib
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    try:
        tomllib = importlib.import_module("tomli")
    except ModuleNotFoundError:
        tomllib = None


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = BASE_DIR / "conf.toml"
CONFIG_TEMPLATE_FILE = BASE_DIR / "conf.toml.template"


DEFAULT_CONFIG = {
    "github": {
        # Deployment-specific values belong in conf.toml (gitignored), not here.
        "base_url": "https://api.github.com",
        "reviewer": "",
        "days_back": 7,
        "max_files": 20,
    },
    "workflow": {
        "mode": "summaries",
        "repos_file": "repos.txt",
    },
    "output": {
        "json_file": "pr_summaries.json",
        "text_file": "pr_summaries.txt",
    },
    "llm": {
        "model_id": "codellama/CodeLlama-7b-hf",
        "task": "text-generation",
    },
}

VALID_MODES = {"summaries", "fetch_only"}


def default_config() -> dict:
    return {section: values.copy() for section, values in DEFAULT_CONFIG.items()}


def config_template_text() -> str:
    """Pretext shown in the GUI when no conf.toml is present."""
    for path in (CONFIG_FILE, CONFIG_TEMPLATE_FILE):
        if path.exists() and path.stat().st_size > 0:
            return path.read_text()
    return _render_toml(DEFAULT_CONFIG)


def parse_config(text: str) -> dict:
    """Merge TOML text over the defaults and validate the result."""
    if tomllib is None:
        raise RuntimeError("Install tomli or use Python 3.11+ to read TOML config")

    config = default_config()
    file_config = tomllib.loads(text) if text and text.strip() else {}

    for section, values in file_config.items():
        if isinstance(values, dict):
            config.setdefault(section, {}).update(values)

    return _validate(config)


def load_config(fallback_text: str | None = None) -> dict:
    """Load config from conf.toml; fall back to the supplied TOML text when absent."""
    if CONFIG_FILE.exists() and CONFIG_FILE.stat().st_size > 0:
        return parse_config(CONFIG_FILE.read_text())

    return parse_config(fallback_text or "")


def _validate(config: dict) -> dict:
    mode = config["workflow"]["mode"]
    if mode not in VALID_MODES:
        raise ValueError(f"workflow.mode must be one of {sorted(VALID_MODES)}, got {mode!r}")

    try:
        config["github"]["days_back"] = int(config["github"]["days_back"])
        config["github"]["max_files"] = int(config["github"].get("max_files", 20))
    except (TypeError, ValueError) as e:
        raise ValueError(f"github.days_back and github.max_files must be integers: {e}") from e

    if not str(config["github"].get("base_url", "")).startswith(("http://", "https://")):
        raise ValueError("github.base_url must be an http(s) URL")

    if not str(config["github"].get("reviewer", "")).strip():
        raise ValueError("github.reviewer must not be empty")

    return config


def _render_toml(config: dict) -> str:
    lines = []
    for section, values in config.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            rendered = f'"{value}"' if isinstance(value, str) else str(value)
            lines.append(f"{key} = {rendered}")
        lines.append("")
    return "\n".join(lines)
