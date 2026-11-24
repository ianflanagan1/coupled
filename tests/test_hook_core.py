"""What the hooks decide, given a file's text and the change a tool call makes to it."""

from coupled_tags_lint.core.hook import (
    MAX_SITES,
    Group,
    Replace,
    Rewrite,
    context,
    gate_reason,
    keys_in,
    touched_keys,
)

CONTENT = "\n".join(
    [
        "import os",  # 0
        "MAX = 8  # COUPLED:upload-limit: app",  # 1
        "# COUPLED:node-version: docker",  # 2
        "# Pinned for the build.",  # 3
        "FROM node:24",  # 4
        "# COUPLED:vat: cart",  # 5
        "def vat(n):",  # 6
        "    return n / 5",  # 7
        "# COUPLED:vat:END",  # 8
        "print(1)",  # 9
    ]
)


def test_an_edit_to_a_marked_line_touches_its_group() -> None:
    assert touched_keys("a.py", CONTENT, [Replace("MAX = 8", False)]) == ["upload-limit"]


def test_an_edit_to_the_line_a_marker_above_describes_touches_its_group() -> None:
    assert touched_keys("a.py", CONTENT, [Replace("FROM node:24", False)]) == ["node-version"]


def test_an_edit_inside_a_block_touches_its_group() -> None:
    assert touched_keys("a.py", CONTENT, [Replace("return n / 5", False)]) == ["vat"]


def test_an_edit_to_unmarked_lines_touches_nothing() -> None:
    assert touched_keys("a.py", CONTENT, [Replace("print(1)", False)]) == []
    assert touched_keys("a.py", CONTENT, [Replace("import os", False)]) == []


def test_replacing_every_occurrence_touches_every_one() -> None:
    content = "a = 1\nb = 1  # COUPLED:x: b"
    assert touched_keys("a.py", content, [Replace("= 1", False)]) == []
    assert touched_keys("a.py", content, [Replace("= 1", True)]) == ["x"]


def test_a_write_touches_the_groups_whose_lines_it_changes() -> None:
    changed = CONTENT.replace("MAX = 8", "MAX = 9")
    assert touched_keys("a.py", CONTENT, [Rewrite(changed)]) == ["upload-limit"]
    assert touched_keys("a.py", CONTENT, [Rewrite(CONTENT + "\nmore()")]) == []


def test_the_keys_in_a_file_are_each_of_its_markers_keys_once() -> None:
    assert keys_in(CONTENT) == ["upload-limit", "node-version", "vat"]


def test_the_gate_reason_lists_each_group_s_sites_and_table() -> None:
    group = Group(
        "upload-limit",
        ["app.py:2:MAX = 8  # COUPLED:upload-limit: app"],
        '["COUPLED:upload-limit:"]\nrelations = ["proxy >= app"]',
    )
    reason = gate_reason([group], ".coupled-tags.toml")
    assert reason.startswith("This edit touches lines marked COUPLED:upload-limit:")
    assert "app.py:2:MAX = 8" in reason
    assert 'Its table in .coupled-tags.toml:\n["COUPLED:upload-limit:"]' in reason
    assert "Then retry this call." in reason


def test_a_group_found_outside_a_work_tree_says_what_to_search_for() -> None:
    text = context("a.py", [Group("x", None, None)], ".coupled-tags.toml")
    assert "Search for `COUPLED:x:`" in text
    assert "It has no table in .coupled-tags.toml" in text


def test_a_long_list_of_sites_is_cut_short() -> None:
    sites = [f"a.py:{n}:X = 1  # COUPLED:x: s{n}" for n in range(MAX_SITES + 5)]
    text = context("a.py", [Group("x", sites, None)], ".coupled-tags.toml")
    assert "... and 5 more" in text


def test_an_edit_below_a_marker_in_a_language_s_own_comment_touches_its_group() -> None:
    content = "\n".join(["% COUPLED:limit: erlang", "% Pinned.", "-define(LIMIT, 8)."])
    assert touched_keys("limits.erl", content, [Replace("LIMIT, 8", False)]) == ["limit"]
