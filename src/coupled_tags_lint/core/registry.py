"""The registry: a repository's record of its COUPLED groups, `coupled-tags-registry.toml` by
default.

    version = 1

    ["COUPLED:upload-limit:"]
    relations = ["proxy >= app", "proxy = ./limits.json#/upload_mb"]
    files = ["./.env?"]
    select = { app = 'MAX_UPLOAD_MB = (\\d+)' }

Each group is a table named as the marker's key is searched for, so a search for
`COUPLED:upload-limit:` finds the group's table beside its sites. `relations` relates its sites,
by their markers' labels, and the files that can't hold a marker (see relations.py); `files`
lists files in the group that no relation names, for a group whose relation is a bare op;
`select` gives a regex picking a site's value out of its line, by its label.

Below the groups, `--update` writes the reviewed section: each group as it was last reviewed, by
a fingerprint of its table, and each of its sites, with the unit on its value in a group of
value ops, or a fingerprint of its block in a group of structural ops. A group that differs from
it fails until it's reviewed and recorded again.
"""

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from typing import final

from coupled_tags_lint.core.markers import NAME_PATTERN
from coupled_tags_lint.core.relations import (
    FileRef,
    Relation,
    parse_file,
    parse_relation,
    refs,
)

REVIEWED_HEADER = (
    "# Written by coupled-tags-lint --update: each group as it was last reviewed. Don't edit "
    "below this line."
)

_VERSION = 1
_GROUP = re.compile(rf"COUPLED:({NAME_PATTERN}):")
_GROUP_FIELDS = ("relations", "files", "select")


@final
@dataclass(frozen=True)
class Group:
    """A group's table: its relations, the files it lists, and a selector for each label that
    has one. problems are what's wrong with the table, as messages saying how to fix it;
    definition is a fingerprint of what it states."""

    key: str
    relations: tuple[Relation, ...]
    files: tuple[FileRef, ...]
    selectors: tuple[tuple[str, str], ...]
    problems: tuple[str, ...]
    definition: str

    def selector(self, label: str) -> str | None:
        for name, regex in self.selectors:
            if name == label:
                return regex
        return None

    def file_refs(self) -> list[FileRef]:
        """Every file in the group, as first written, each once however it's marked."""
        found: list[FileRef] = []
        named = [ref for relation in self.relations for ref in refs(relation)]
        for ref in [*self.files, *named]:
            if isinstance(ref, FileRef) and ref.unmarked() not in [f.unmarked() for f in found]:
                found.append(ref)
        return found


@final
@dataclass(frozen=True)
class ReviewedSite:
    """A site as the reviewed section records it: its marker (`COUPLED:<key>: <label>`), or a
    file's ref, with the unit on its value and the fingerprint of its block, where recorded."""

    name: str
    unit: str | None
    block: str | None


@final
@dataclass(frozen=True)
class Reviewed:
    definition: str
    sites: tuple[ReviewedSite, ...]


@final
@dataclass(frozen=True)
class Registry:
    """The registry's groups and reviewed section, by key, and what's wrong with it beyond its
    groups' own problems."""

    groups: dict[str, Group]
    reviewed: dict[str, Reviewed]
    problems: tuple[str, ...]


@final
@dataclass(frozen=True)
class Unparseable:
    reason: str


def table_name(key: str) -> str:
    """The name of key's table, as written in the registry: `["COUPLED:<key>:"]`."""
    return f'["COUPLED:{key}:"]'


def parse(text: str) -> Registry | Unparseable:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        return Unparseable(f"it isn't TOML: {error}")
    if data.get("version") != _VERSION:
        return Unparseable(f"it needs `version = {_VERSION}` at its top")
    groups: dict[str, Group] = {}
    problems: list[str] = []
    for name, table in data.items():
        if name in ("version", "reviewed"):
            continue
        match = _GROUP.fullmatch(name)
        if match is None or not isinstance(table, dict):
            problems.append(
                f"Drop `{name}`, or name a group's table as its markers are searched for: "
                '["COUPLED:<key>:"]'
            )
            continue
        groups[match.group(1)] = _group(match.group(1), table)
    reviewed, reviewed_problems = _reviewed(data.get("reviewed", {}))
    return Registry(groups, reviewed, tuple(problems + reviewed_problems))


def _group(key: str, table: dict[str, object]) -> Group:
    problems: list[str] = []
    for field in sorted(table.keys() - set(_GROUP_FIELDS)):
        problems.append(f"Drop `{field}`: a group's table holds {', '.join(_GROUP_FIELDS)}")
    relations: list[Relation] = []
    written = _strings(table.get("relations"), "relations", problems)
    if not written and "relations" not in table:
        problems.append('Give the group `relations = [...]`, such as `["a = b"]` or `["="]`')
    for text in written:
        parsed = parse_relation(text)
        if isinstance(parsed, str):
            problems.append(parsed)
        else:
            relations.append(parsed)
    files: list[FileRef] = []
    for text in _strings(table.get("files"), "files", problems):
        ref = parse_file(text)
        if ref is None:
            problems.append(f"Write each of `files` as ./<path>[?][#<pointer>]: `{text}` isn't")
        else:
            files.append(ref)
    selectors: list[tuple[str, str]] = []
    select = table.get("select", {})
    if not isinstance(select, dict) or not all(isinstance(regex, str) for regex in select.values()):
        problems.append("Write `select` as a table of regexes by label: `{ app = '(\\d+)' }`")
    else:
        selectors = sorted((str(label), str(regex)) for label, regex in select.items())
    definition = _fingerprint(
        [*(f"relation {' '.join(text.split())}" for text in written)]
        + [f"file {text}" for text in _strings(table.get("files"), "files", [])]
        + [f"select {label} {regex}" for label, regex in selectors]
    )
    return Group(key, tuple(relations), tuple(files), tuple(selectors), tuple(problems), definition)


def _strings(value: object, field: str, problems: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        problems.append(f"Write `{field}` as a list of strings")
        return []
    return [str(item) for item in value]


def _reviewed(data: object) -> tuple[dict[str, Reviewed], list[str]]:
    broken = (
        {},
        [
            f"Can't read the reviewed section. Delete it, from `{REVIEWED_HEADER[:30]}...`, then "
            "review every group and rerun with --update"
        ],
    )
    if not isinstance(data, dict):
        return broken
    reviewed: dict[str, Reviewed] = {}
    for name, table in data.items():
        match = _GROUP.fullmatch(name)
        if match is None or not isinstance(table, dict):
            return broken
        definition = table.get("definition")
        if not isinstance(definition, str):
            return broken
        sites: list[ReviewedSite] = []
        for site, fields in table.items():
            if site == "definition":
                continue
            if not isinstance(fields, dict):
                return broken
            unit, block = fields.get("unit"), fields.get("block")
            if not isinstance(unit, str | None) or not isinstance(block, str | None):
                return broken
            sites.append(ReviewedSite(site, unit, block))
        reviewed[match.group(1)] = Reviewed(definition, tuple(sites))
    return reviewed, []


def with_reviewed(text: str, reviewed: dict[str, Reviewed]) -> str:
    """The registry text with its reviewed section written as reviewed: every line from the
    section's header, or its first table if the header is gone, is replaced."""
    lines = text.splitlines()
    cut = len(lines)
    for index, line in enumerate(lines):
        if line.strip() == REVIEWED_HEADER or line.startswith("[reviewed."):
            cut = index
            break
    authored = "\n".join(lines[:cut]).rstrip() + "\n"
    if not reviewed:
        return authored
    tables = []
    for key in sorted(reviewed):
        group = reviewed[key]
        rows = [f"[reviewed.{json.dumps(f'COUPLED:{key}:')}]"]
        rows.append(f"definition = {json.dumps(group.definition)}")
        for site in sorted(group.sites, key=lambda site: site.name):
            fields = [
                f"{name} = {json.dumps(value)}"
                for name, value in (("unit", site.unit), ("block", site.block))
                if value is not None
            ]
            inline = "{ " + ", ".join(fields) + " }" if fields else "{}"
            rows.append(f"{json.dumps(site.name)} = {inline}")
        tables.append("\n".join(rows))
    return authored + "\n" + REVIEWED_HEADER + "\n\n" + "\n\n".join(tables) + "\n"


def entry_text(text: str, key: str) -> str | None:
    """The lines of key's table in the registry text, as written, or None if it has none."""
    lines = text.splitlines()
    header = table_name(key)
    start = next((n for n, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        return None
    end = start + 1
    while (
        end < len(lines)
        and not lines[end].startswith("[")
        and (lines[end].strip() != REVIEWED_HEADER)
    ):
        end += 1
    return "\n".join(lines[start:end]).rstrip()


def _fingerprint(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
