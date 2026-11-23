"""Behaviour of the coupled-tags-lint command, run as a program. The rules for markers, the
registry and values are tested in test_markers.py, test_registry.py, test_values.py and
test_check.py.

Each test writes its files into a fresh directory that isn't a git work tree, so the lint falls
back to grep. A test that reads the clean status line records the groups as reviewed first, with
--update, so the reviewed section's own problems don't join in.
"""

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

SETTINGS = ".config/ianf-coupled-tags.toml"


@dataclass(frozen=True)
class Ran:
    status: int
    output: str
    errors: str


class Sandbox:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "repo"
        self.repo.mkdir()

    def file(self, name: str, *lines: str) -> None:
        """Writes the lines to name in the repository."""
        _write(self.repo / name, lines)

    def run(self, *args: str, cwd: Path | None = None) -> Ran:
        env = {**os.environ, "NO_COLOR": "1"}
        env.pop("FORCE_COLOR", None)
        done = subprocess.run(
            [sys.executable, "-m", "coupled_tags_lint", *args],
            cwd=cwd or self.root,
            env=env,
            capture_output=True,
            text=True,
        )
        return Ran(done.returncode, done.stdout, done.stderr)

    def lint(self, *options: str) -> Ran:
        return self.run(*options, str(self.repo))

    def registry(self, *lines: str) -> None:
        """Writes the registry, its version and then the lines."""
        self.file(".coupled-tags.toml", "version = 1", *lines)

    def review(self) -> None:
        """Records the groups as they are now in the registry's reviewed section."""
        self.lint("--update")

    def git_init(self) -> None:
        subprocess.run(["git", "init", "--quiet"], cwd=self.repo, check=True)


def _write(path: Path, lines: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in lines))


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path.resolve())


def assert_clean(ran: Ran) -> None:
    assert ran.status == 0, f"unexpected problems: {ran.errors}"


def assert_problem(ran: Ran, text: str) -> None:
    assert ran.status == 1
    assert text in ran.errors


# --- Repositories

UPLOAD = ('["COUPLED:upload-limit:"]', 'relations = ["nginx >= app"]')
MESSAGE = 'Change only with every "COUPLED:upload-limit:" site, per .coupled-tags.toml.'


def upload(sandbox: Sandbox, app_limit: int) -> None:
    sandbox.file("app.py", f"MAX_UPLOAD_MB = {app_limit}  # COUPLED:upload-limit: app")
    sandbox.file("nginx.conf", "client_max_body_size 10m;  # COUPLED:upload-limit: nginx")
    sandbox.registry(*UPLOAD)


def test_a_group_whose_values_agree_across_files_is_clean(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    sandbox.review()
    ran = sandbox.lint()
    assert_clean(ran)
    assert ran.output == "➖ No problems in 1 COUPLED key.\n"


def test_a_relation_that_fails_is_reported_at_its_site(sandbox: Sandbox) -> None:
    upload(sandbox, 12)
    sandbox.review()
    assert_problem(
        sandbox.lint(), "nginx.conf:1 `nginx >= app` doesn't hold with app.py:1: 10m >= 12"
    )


def test_problems_are_counted_in_the_status_line_before_them(sandbox: Sandbox) -> None:
    upload(sandbox, 12)
    ran = sandbox.lint()
    assert ran.status == 1
    assert ran.errors.splitlines()[0] == "⚠️ 2 problems in COUPLED groups."


def test_a_marker_on_a_comment_line_is_checked_against_the_line_below(sandbox: Sandbox) -> None:
    sandbox.file("Dockerfile", "# COUPLED:node-version: docker", "FROM node:24.1-slim")
    sandbox.file("compose.yaml", "image: node:22.3-alpine  # COUPLED:node-version: compose")
    sandbox.registry('["COUPLED:node-version:"]', 'relations = ["="]')
    assert_problem(sandbox.lint(), "compose.yaml:1 `=` doesn't hold with Dockerfile:1: 22.3 = 24.1")


def test_a_search_for_the_key_finds_the_group_s_table_beside_its_sites(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    found = subprocess.run(
        ["grep", "-r", "-l", "COUPLED:upload-limit:", "."],
        cwd=sandbox.repo,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert sorted(found) == ["./.coupled-tags.toml", "./app.py", "./nginx.conf"]


def test_markers_with_no_registry_are_reported(sandbox: Sandbox) -> None:
    sandbox.file("app.py", "MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app")
    assert_problem(sandbox.lint(), ".coupled-tags.toml There's no registry.")


def test_in_a_git_work_tree_ignored_files_are_skipped(sandbox: Sandbox) -> None:
    sandbox.git_init()
    sandbox.file(".gitignore", "build/")
    upload(sandbox, 8)
    sandbox.file("build/b.py", "X = 1  # COUPLED:other-limit: b")
    sandbox.review()
    assert_clean(sandbox.lint())


def test_a_directory_given_by_a_relative_path_is_scanned(sandbox: Sandbox) -> None:
    sandbox.git_init()
    sandbox.file("a.py", "X = 1  # COUPLED:x-limit: a")
    assert_problem(sandbox.run("repo", cwd=sandbox.root), "There's no registry")


def test_an_excluded_path_is_skipped(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    sandbox.file("docs/b.py", "X = 2  # COUPLED:upload-limit: app")
    sandbox.lint("--update", "-x", "docs/")
    assert_clean(sandbox.lint("-x", "docs/"))


def test_a_path_the_settings_file_excludes_is_skipped(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    sandbox.file("docs/b.py", "X = 2  # COUPLED:upload-limit: app")
    sandbox.file(SETTINGS, "version = 1", 'exclude = ["docs/"]')
    sandbox.review()
    assert_clean(sandbox.lint())


def test_an_excluded_path_adds_to_the_settings_file_s(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    sandbox.file("docs/b.py", "X = 2  # COUPLED:upload-limit: app")
    sandbox.file("build/c.py", "X = 3  # COUPLED:upload-limit: app")
    sandbox.file(SETTINGS, "version = 1", 'exclude = ["docs"]')
    sandbox.lint("--update", "-x", "build")
    assert_clean(sandbox.lint("-x", "build"))


def test_a_settings_file_with_no_version_is_reported_and_nothing_is_changed(
    sandbox: Sandbox,
) -> None:
    upload(sandbox, 8)
    sandbox.file(SETTINGS, 'exclude = ["docs"]')
    before = (sandbox.repo / ".coupled-tags.toml").read_text()
    ran = sandbox.lint("--update")
    assert ran.status == 1
    assert ran.errors.startswith("⚠️ No version in ")
    assert (sandbox.repo / ".coupled-tags.toml").read_text() == before


def test_a_setting_the_lint_does_not_know_is_reported(sandbox: Sandbox) -> None:
    sandbox.file(SETTINGS, "version = 1", "skip = []")
    assert_problem(sandbox.lint(), "ianf-coupled-tags.toml: skip.")


def test_the_registry_is_the_file_the_settings_file_names(sandbox: Sandbox) -> None:
    sandbox.file("app.py", "MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app")
    sandbox.file("nginx.conf", "client_max_body_size 10m;  # COUPLED:upload-limit: nginx")
    sandbox.file(".config/coupled.toml", "version = 1", *UPLOAD)
    sandbox.file(SETTINGS, "version = 1", 'registry = ".config/coupled.toml"')
    sandbox.review()
    assert_clean(sandbox.lint())
    assert "[reviewed." in (sandbox.repo / ".config/coupled.toml").read_text()


def test_a_registry_outside_the_repository_is_reported(sandbox: Sandbox) -> None:
    sandbox.file(SETTINGS, "version = 1", 'registry = "../coupled.toml"')
    assert_problem(sandbox.lint(), "must be the path of a file inside the repository")


def test_list_prints_every_key_and_its_sites(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    ran = sandbox.lint("-l")
    assert "upload-limit (2)" in ran.output
    assert "    app.py:1" in ran.output


def test_a_marked_file_that_is_not_utf8_is_reported(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    (sandbox.repo / "latin.txt").write_bytes(b"caf\xe9  # COUPLED:upload-limit: x\n")
    assert_problem(sandbox.lint(), "latin.txt Can't read this file as UTF-8")


# --- Files that can't hold a marker


def test_a_pointer_into_json_is_checked(sandbox: Sandbox) -> None:
    sandbox.file("nginx.conf", "client_max_body_size 10m;  # COUPLED:upload-limit: nginx")
    sandbox.file("limits.json", '{"upload_mb": 12}')
    sandbox.registry(
        '["COUPLED:upload-limit:"]', 'relations = ["nginx >= ./limits.json#/upload_mb"]'
    )
    assert_problem(sandbox.lint(), "doesn't hold with ./limits.json#/upload_mb: 10m >= 12")


def test_a_group_of_two_files_that_cannot_hold_markers_is_checked(sandbox: Sandbox) -> None:
    sandbox.file(".nvmrc", "24")
    sandbox.file(".tool-version", "22")
    sandbox.registry('["COUPLED:node-version:"]', 'relations = ["./.nvmrc = ./.tool-version"]')
    assert_problem(sandbox.lint(), "./.nvmrc `./.nvmrc = ./.tool-version` doesn't hold")


def test_a_missing_file_is_reported_unless_it_is_optional(sandbox: Sandbox) -> None:
    sandbox.file("a.py", "X = 1  # COUPLED:x: a")
    sandbox.registry('["COUPLED:x:"]', 'relations = ["="]', 'files = ["./.nvmrc", "./.env?"]')
    ran = sandbox.lint()
    assert_problem(ran, "./.nvmrc COUPLED:x: names this file, but it isn't there")
    assert "./.env" not in ran.errors


def test_other_repositories_are_named_as_not_checked(sandbox: Sandbox) -> None:
    sandbox.file("a.go", "type listing struct {  // COUPLED:listing-shape: go")
    sandbox.registry(
        '["COUPLED:listing-shape:"]',
        'relations = ["go same-shape //github.com/me/rulebook/schema/coverage.json"]',
    )
    sandbox.review()
    ran = sandbox.lint()
    assert_clean(ran)
    assert "Not checked, as they're other repositories: github.com/me/rulebook." in ran.output


# --- The tag message


def test_fix_writes_the_message_when_the_settings_turn_it_on(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    sandbox.file(SETTINGS, "version = 1", "tag-message = true")
    assert_problem(sandbox.lint(), "--fix writes it")
    sandbox.lint("--fix", "--update")
    assert (sandbox.repo / "app.py").read_text() == (
        f"MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app. {MESSAGE}\n"
    )
    assert_clean(sandbox.lint())


def test_fix_drops_the_message_when_the_settings_turn_it_off(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    sandbox.file("app.py", f"MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app. {MESSAGE}")
    assert_problem(sandbox.lint(), "--fix drops it")
    sandbox.lint("--fix", "--update")
    assert (
        sandbox.repo / "app.py"
    ).read_text() == "MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app\n"


# --- The reviewed section


def test_update_records_the_groups_in_the_registry(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    ran = sandbox.lint("--update")
    assert_clean(ran)
    text = (sandbox.repo / ".coupled-tags.toml").read_text()
    assert '[reviewed."COUPLED:upload-limit:"]' in text
    assert '"COUPLED:upload-limit: nginx" = { unit = "m" }' in text
    assert "Updated .coupled-tags.toml." in ran.output


def test_update_records_the_groups_even_when_relations_fail(sandbox: Sandbox) -> None:
    upload(sandbox, 12)
    ran = sandbox.lint("--update")
    assert "Updated .coupled-tags.toml." in ran.errors
    assert "hasn't been reviewed" not in ran.errors


def test_a_group_that_was_never_reviewed_is_reported(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    assert_problem(sandbox.lint(), "COUPLED:upload-limit: hasn't been reviewed")


def test_an_edited_structural_block_fails_until_it_is_reviewed(sandbox: Sandbox) -> None:
    sandbox.file(
        "a.py", "# COUPLED:vat: invoice", "def vat(n):", "    return n / 5", "# COUPLED:vat:END"
    )
    sandbox.file(
        "b.py", "# COUPLED:vat: cart", "def vat(n):", "    return n / 5", "# COUPLED:vat:END"
    )
    sandbox.registry('["COUPLED:vat:"]', 'relations = ["same-as"]')
    sandbox.review()
    sandbox.file(
        "a.py", "# COUPLED:vat: invoice", "def vat(n):", "    return n / 6", "# COUPLED:vat:END"
    )
    assert_problem(sandbox.lint(), "a.py:1 It has changed since it was last reviewed")
    sandbox.review()
    assert_clean(sandbox.lint())


def test_an_end_after_a_marker_of_a_value_group_is_reported(sandbox: Sandbox) -> None:
    upload(sandbox, 8)
    sandbox.file(
        "app.py", "MAX_UPLOAD_MB = 8  # COUPLED:upload-limit: app", "# COUPLED:upload-limit:END"
    )
    assert_problem(sandbox.lint(), "app.py:1 Drop the END")


# --- Exit status


def test_a_directory_with_no_markers_exits_zero(sandbox: Sandbox) -> None:
    sandbox.file("a.py", "X = 1")
    ran = sandbox.lint()
    assert_clean(ran)
    assert ran.output == "➖ No COUPLED markers.\n"


def test_help_describes_the_options(sandbox: Sandbox) -> None:
    ran = sandbox.run("-h")
    assert ran.status == 0
    assert "usage: coupled-tags-lint [-h] [-l] [-x <path>] [--fix] [--update] [<dir>]" in ran.output
    assert "exclude a path prefix" in ran.output
    assert "Exit status: 0 clean, 1 problems found, 2 usage error." in ran.output


def test_an_unknown_option_is_a_usage_error(sandbox: Sandbox) -> None:
    assert sandbox.lint("-q").status == 2


def test_a_directory_that_does_not_exist_is_a_usage_error(sandbox: Sandbox) -> None:
    assert sandbox.run(str(sandbox.root / "missing")).status == 2
