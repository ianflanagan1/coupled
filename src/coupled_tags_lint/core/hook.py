"""What the Claude Code hooks decide: which groups an edit touches, which a file holds, and what
to tell Claude about them.

The gate, before an Edit, MultiEdit or Write, looks for the markers covering the lines the call
changes: a marker's own line, the line it describes, and down to the END closing its block. The
context hook, after a Read, looks for every marker in the file read. Each shows Claude the
groups it finds, their sites and their tables, once a session.
"""

import difflib
from dataclasses import dataclass
from typing import assert_never, final

from coupled_tags_lint.core.comments import syntax_of
from coupled_tags_lint.core.markers import End, Malformed, Marker, find_markers
from coupled_tags_lint.core.values import described_line

# At most this many sites are listed for a group, each cut to this length.
MAX_SITES = 40
_MAX_SITE_LENGTH = 200


@final
@dataclass(frozen=True)
class Replace:
    """An edit replacing old, its first occurrence or every one."""

    old: str
    every: bool


@final
@dataclass(frozen=True)
class Rewrite:
    """A write replacing the whole file with content."""

    content: str


type Change = Replace | Rewrite


def touched_keys(path: str, content: str, changes: list[Change]) -> list[str]:
    """The keys of the markers covering the lines of content, the file at path, that changes
    alter, in order."""
    lines = content.splitlines()
    ranges: list[tuple[int, int]] = []
    for change in changes:
        match change:
            case Replace(old, every):
                ranges += _ranges_of(content, old, every)
            case Rewrite(new):
                ranges += _changed_ranges(content, new)
            case _:
                assert_never(change)
    keys: list[str] = []
    for placed in find_markers(lines):
        match placed.found:
            case Marker(key=key):
                described = described_line(lines, placed.line, syntax_of(path))
                reach = placed.close if placed.close is not None else described
                reach = placed.line if reach is None else max(reach, placed.line)
            case End(key=key):
                reach = placed.line
            case Malformed():
                continue
            case _:
                assert_never(placed.found)
        if key in keys:
            continue
        if any(first <= reach and last >= placed.line for first, last in ranges):
            keys.append(key)
    return keys


def keys_in(content: str) -> list[str]:
    """The keys of the markers in content, in order, each once."""
    keys: list[str] = []
    for placed in find_markers(content.splitlines()):
        if isinstance(placed.found, Marker) and placed.found.key not in keys:
            keys.append(placed.found.key)
    return keys


def _ranges_of(content: str, old: str, every: bool) -> list[tuple[int, int]]:
    """The [first, last] line indexes of old in content: its first occurrence, or every one."""
    ranges: list[tuple[int, int]] = []
    start = content.find(old) if old else -1
    while start != -1:
        first = content.count("\n", 0, start)
        ranges.append((first, first + old.count("\n")))
        if not every:
            break
        start = content.find(old, start + len(old))
    return ranges


def _changed_ranges(before: str, after: str) -> list[tuple[int, int]]:
    """The [first, last] line indexes in before that writing after would change or insert at."""
    old_lines = before.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, after.splitlines(), autojunk=False)
    return [
        (i1, max(i1, i2 - 1))
        for tag, i1, i2, _, _ in matcher.get_opcodes()
        if tag != "equal" and i1 < max(len(old_lines), 1)
    ]


@final
@dataclass(frozen=True)
class Group:
    """What the hooks show of a group: its sites as `path:line:text`, or None outside a git work
    tree, where they weren't searched for, and its table in the registry, or None if it has
    none."""

    key: str
    sites: list[str] | None
    table: str | None


_ACT = (
    "change them together so every relation still holds, then run coupled-tags-lint. Change a "
    "group's table only if what must hold has changed, and once every site is reviewed, record "
    "it with `coupled-tags-lint --update <key>`."
)


def gate_reason(groups: list[Group], registry_file: str) -> str:
    """Why the gate stops an edit touching groups, and what Claude should do first."""
    keys = ", ".join(f"COUPLED:{group.key}:" for group in groups)
    head = (
        f"This edit touches lines marked {keys}, which must change together with the rest of "
        "their group. Before changing them, read every site below and the group's table, "
        f"{_ACT} Then retry this call."
    )
    return "\n\n".join([head, *(_describe(group, registry_file) for group in groups)])


def context(path: str, groups: list[Group], registry_file: str) -> str:
    """What the context hook tells Claude about the groups in the file at path."""
    head = (
        f"{path} has COUPLED markers: each marked line must change together with the rest of "
        "its group. Before changing one, read every site of its group below and its table, "
        f"{_ACT}"
    )
    return "\n\n".join([head, *(_describe(group, registry_file) for group in groups)])


def _describe(group: Group, registry_file: str) -> str:
    search = f"COUPLED:{group.key}:"
    if group.sites is None:
        sites = f"Search for `{search}` to find its sites."
    else:
        shown = [site.strip()[:_MAX_SITE_LENGTH] for site in group.sites[:MAX_SITES]]
        if len(group.sites) > MAX_SITES:
            shown.append(f"... and {len(group.sites) - MAX_SITES} more")
        sites = f"{search} sites:\n" + "\n".join(shown)
    if group.table is None:
        table = f"It has no table in {registry_file}, so its relations aren't recorded."
    else:
        table = f"Its table in {registry_file}:\n{group.table}"
    return f"{sites}\n{table}"
