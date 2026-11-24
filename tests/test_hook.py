"""Behaviour of the coupled-hook command, run as a program on a hook event, as Claude Code
runs it. What it decides from a file's text is tested in test_hook_core.py.

Each test writes a git work tree, and gives the hook its own session and temporary directory, so
the groups it has shown are its own.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

MARKED = "MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app"


class Repo:
    def __init__(self, root: Path) -> None:
        self.root = root / "repo"
        self.root.mkdir()
        self.state = root / "tmp"
        self.state.mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=self.root, check=True)
        self.file("app.py", "import os", MARKED)
        self.file("nginx.conf", "client_max_body_size 10m;  # COUPLED:upload-limit: proxy")
        self.file(
            "coupled-registry.toml",
            "version = 1",
            '["COUPLED:upload-limit:"]',
            'relations = ["proxy >= app"]',
        )

    def file(self, name: str, *lines: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(line + "\n" for line in lines))

    def hook(self, event: dict[str, object]) -> dict[str, object] | None:
        """The hook's JSON reply to event, or None if it said nothing."""
        done = subprocess.run(
            [sys.executable, "-c", "from coupled.__main__ import hook; hook()"],
            input=json.dumps(event),
            env={**os.environ, "TMPDIR": str(self.state)},
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(done.stdout) if done.stdout.strip() else None

    def edit(self, session: str, name: str, old: str) -> dict[str, object] | None:
        return self.hook(
            {
                "hook_event_name": "PreToolUse",
                "session_id": session,
                "tool_name": "Edit",
                "tool_input": {"file_path": str(self.root / name), "old_string": old},
            }
        )

    def read(self, session: str, name: str) -> dict[str, object] | None:
        return self.hook(
            {
                "hook_event_name": "PostToolUse",
                "session_id": session,
                "tool_name": "Read",
                "tool_input": {"file_path": str(self.root / name)},
            }
        )


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path.resolve())


def _output(reply: dict[str, object] | None) -> dict[str, object]:
    assert reply is not None
    output = reply["hookSpecificOutput"]
    assert isinstance(output, dict)
    return output


def test_the_gate_stops_the_first_edit_to_a_marked_line_with_its_group(repo: Repo) -> None:
    output = _output(repo.edit("s1", "app.py", MARKED))
    assert output["permissionDecision"] == "deny"
    reason = str(output["permissionDecisionReason"])
    assert "app.py:2:MAX_UPLOAD_MB = 8" in reason
    assert "nginx.conf:1:client_max_body_size 10m;" in reason
    assert 'relations = ["proxy >= app"]' in reason


def test_the_gate_lets_later_edits_to_the_group_through(repo: Repo) -> None:
    repo.edit("s1", "app.py", MARKED)
    assert repo.edit("s1", "app.py", MARKED) is None
    assert repo.edit("s1", "nginx.conf", "client_max_body_size") is None


def test_the_gate_lets_an_edit_to_unmarked_lines_through(repo: Repo) -> None:
    assert repo.edit("s1", "app.py", "import os") is None


def test_reading_a_marked_file_shows_its_groups(repo: Repo) -> None:
    output = _output(repo.read("s1", "app.py"))
    text = str(output["additionalContext"])
    assert text.startswith("app.py has COUPLED markers")
    assert "nginx.conf:1:" in text
    assert '["COUPLED:upload-limit:"]' in text


def test_a_group_shown_on_reading_is_not_gated_again(repo: Repo) -> None:
    repo.read("s1", "app.py")
    assert repo.edit("s1", "app.py", MARKED) is None


def test_reading_a_file_with_no_markers_says_nothing(repo: Repo) -> None:
    repo.file("plain.py", "x = 1")
    assert repo.read("s1", "plain.py") is None


def test_each_session_is_shown_a_group_once(repo: Repo) -> None:
    assert repo.read("s1", "app.py") is not None
    assert repo.read("s1", "app.py") is None
    assert repo.read("s2", "app.py") is not None


def test_files_the_settings_exclude_are_left_alone(repo: Repo) -> None:
    repo.file("docs/example.md", "COUPLED:upload-limit: example")
    repo.file(".config/coupled.toml", "version = 1", 'exclude = ["docs"]')
    assert repo.read("s1", "docs/example.md") is None
    assert "docs/example.md" not in str(_output(repo.read("s2", "app.py"))["additionalContext"])


def test_files_holding_the_ignore_directive_are_left_alone(repo: Repo) -> None:
    repo.file("SKILL.md", "<!-- COUPLED:IGNORE-FILE -->", "COUPLED:upload-limit: example")
    assert repo.read("s1", "SKILL.md") is None
    assert repo.edit("s1", "SKILL.md", "COUPLED:upload-limit: example") is None
    assert "SKILL.md" not in str(_output(repo.read("s2", "app.py"))["additionalContext"])


def test_the_registry_itself_is_left_alone(repo: Repo) -> None:
    assert repo.read("s1", "coupled-registry.toml") is None


def test_other_tools_and_events_pass_silently(repo: Repo) -> None:
    event = {
        "hook_event_name": "PreToolUse",
        "session_id": "s1",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }
    assert repo.hook(event) is None


def test_a_failure_is_told_to_the_user_and_lets_the_call_through(repo: Repo) -> None:
    done = subprocess.run(
        [sys.executable, "-c", "from coupled.__main__ import hook; hook()"],
        input="not json",
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0
    assert "The coupled hook failed" in json.loads(done.stdout)["systemMessage"]
