"""Smoke tests for the Crew app files: app.json, agent.json, prompt.md, SKILL.md.

Validates: Requirements 1.5, 1.6, 9.1-9.12, 11.7, 11.8
"""

import json
import re
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent
APP_JSON = APP_DIR / "app.json"

ALLOWED_APP_FIELDS = {
    "name", "version", "displayName", "description", "author",
    "license", "agents", "skills", "mcpServers", "crons",
    "permissions",
}
ALLOWED_AGENT_FIELDS = {"name", "model", "description", "prompt", "tools"}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _frontmatter_keys(text: str) -> set[str]:
    """Return the top-level keys in the leading --- block of a Markdown file."""
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", "SKILL.md has no frontmatter"
    keys = set()
    for line in lines[1:]:
        if line.strip() == "---":
            return keys
        match = re.match(r"^([A-Za-z_][\w-]*):", line)
        if match:
            keys.add(match.group(1))
    raise AssertionError("SKILL.md frontmatter is not closed")


@pytest.fixture(scope="module")
def app() -> dict:
    return _load_json(APP_JSON)


@pytest.fixture(scope="module")
def agent_path(app) -> Path:
    return APP_DIR / app["agents"][0]


@pytest.fixture(scope="module")
def agent(agent_path) -> dict:
    return _load_json(agent_path)


@pytest.fixture(scope="module")
def prompt_text() -> str:
    return (APP_DIR / "report_agent" / "prompt.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_text(app) -> str:
    return (APP_DIR / app["skills"][0] / "SKILL.md").read_text(encoding="utf-8")


# ---- app.json ----

def test_app_json_fields_and_values(app):
    assert set(app) <= ALLOWED_APP_FIELDS
    assert app["name"] == "night-watch"
    assert app["version"] == "0.1.0"
    assert app["displayName"] == "Night Watch"
    assert app["license"] == "MIT"
    assert app["description"] and app["author"]


def test_agents_list_points_to_agent_file(app):
    assert app["agents"] == ["report_agent/agent.json"]
    assert (APP_DIR / app["agents"][0]).is_file()


def test_skills_list_points_to_skill_folder(app):
    assert len(app["skills"]) == 1
    assert (APP_DIR / app["skills"][0] / "SKILL.md").is_file()


def test_mcp_server_entry(app):
    servers = app["mcpServers"]
    assert len(servers) == 1
    entry = next(iter(servers.values()))
    assert set(entry) == {"command", "args", "env"}
    assert entry["command"] == "python3"
    assert entry["args"] == ["mcp_server.py"]
    assert (APP_DIR / "mcp_server.py").is_file()


def test_cron_entry(app, agent):
    assert len(app["crons"]) == 1
    cron = app["crons"][0]
    assert set(cron) == {"name", "cron_expr", "message", "agent"}
    assert cron["cron_expr"] == "0 2 * * *"
    assert cron["agent"] == agent["name"]
    message = cron["message"]
    assert "run_night_watch" in message
    assert "all_as_expected" in message
    assert "one line" in message
    assert "prompt.md" in message


# ---- agent.json ----

def test_agent_fields_and_prompt(agent, prompt_text):
    assert set(agent) == ALLOWED_AGENT_FIELDS
    assert agent["model"] == "auto"
    assert agent["prompt"] == prompt_text


# ---- skill ----

def test_skill_frontmatter(skill_text):
    assert _frontmatter_keys(skill_text) >= {"name", "description", "triggers"}


# ---- no API address, no secrets ----

@pytest.mark.parametrize("path", [APP_JSON, APP_DIR / "report_agent" / "agent.json"])
def test_json_files_have_no_address_or_secrets(path):
    text = path.read_text(encoding="utf-8").lower()
    for bad in ("http://", "https://", "127.0.0.1", "localhost", "ha_api_url",
                "password", "secret", "api_key", "apikey", "token", "bearer"):
        assert bad not in text, f"{path.name} contains {bad!r}"


# ---- required rules in prompt and skill ----

@pytest.mark.parametrize("which", ["prompt", "skill"])
def test_rules_present(which, prompt_text, skill_text):
    text = (prompt_text if which == "prompt" else skill_text).lower()
    assert "scripted mode" in text
    assert "wcag" in text and "compliance" in text and "conformance" in text
    assert "final" in text  # the checker's verdict is final
    assert "pull request" in text and "push" in text  # never change anything
    assert "selector" in text and "reason code" in text  # never invent details
    assert "synthetic" in text


# ---- source files ----

def test_sources_have_no_os_path_or_credentials():
    sources = sorted(APP_DIR.glob("*.py"))
    assert sources, "no source files found"
    cred = re.compile(
        r"(password|passwd|secret|api[_-]?key|token|bearer)\s*[=:]\s*['\"][^'\"]+['\"]",
        re.IGNORECASE,
    )
    for src in sources:
        text = src.read_text(encoding="utf-8")
        assert "os.path" not in text, f"{src.name} uses os.path"
        assert not cred.search(text), f"{src.name} looks like it has a credential"
