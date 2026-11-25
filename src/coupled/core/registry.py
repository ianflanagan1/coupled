"""The registry: a repository's record of its COUPLED groups, `coupled-registry.toml` by
default.

    version = 1

    ["COUPLED:upload-limit:"]
    relations = ["cdn >= proxy", "proxy >= app", "proxy = limits", "app = env"]
    has-no-marker.limits = "./limits.json#/upload_mb"
    has-no-marker.env = { file = "./.env?", regex = '^UPLOAD_MB=(\\d+)' }
    has-no-marker.cdn = "//github.com/vendor/cdn/defaults.json#/max_upload_mb"
    in-another-registry = { api = "//github.com/acme/api" }
    has-no-file = { cdn = "the CDN's dashboard > Network > Maximum Upload Size" }

Each group is a table named as the marker's key is searched for, so a search for
`COUPLED:upload-limit:` finds the group's table beside its sites. `relations` relates its sites
by their labels (see relations.py). A site a marker carries takes the marker's label; each other
site gets one in the table, by why it has no marker here: `has-no-marker` gives a file
that holds none, in this repository as `./<path>[?][#<pointer>]`, because it can't hold one or
not where its value is, `?` when it's only sometimes there and the pointer a JSON Pointer to its
value, or in another repository that keeps no such group as
`//<git-host>/<owner>/<name>/<path>[#<pointer>]`, which the lint doesn't read; or either as a
table, `{ file = "<file>", regex = '<regex>' }`, where its regex, if it has one, picks its value,
or each of its members, out of its lines, in place of a pointer;
`in-another-registry` gives another repository that keeps the group too, as
`//<git-host>/<owner>/<name>`, where the label is one of that repository's own sites, which its
markers or its registry describe and the lint doesn't read; and `has-no-file` says where a site
in no file at all is set, such as in a cloud console, which the lint can't read either.
A marker carries its own regex, after its label (see markers.py). `why` says why the sites
must change together, which the lint and the hooks show beside them. A table gives its fields
in that order: relations, has-no-marker, in-another-registry, has-no-file, why. Neither why
nor where a site with no file is set is part of what's reviewed.

Below the groups, `--update` writes the reviewed section: each group as it was last reviewed, by
a fingerprint of its table, and each of its sites, with the unit on its value in a group of
value ops, or a fingerprint of its block in a group of judged ops, and its marker's regex, if it
has one. A group that differs from it
fails until it's reviewed and recorded again.
"""

import hashlib
import json
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import final

from coupled.core.markers import NAME_PATTERN
from coupled.core.relations import LABEL, Relation, parse_relation

REVIEWED_HEADER = (
    "# Written by coupled --update: each group as it was last reviewed. Don't edit below this line."
)

_VERSION = 1
_GROUP = re.compile(rf"COUPLED:({NAME_PATTERN}):")
HAS_NO_MARKER = "has-no-marker"
IN_ANOTHER_REGISTRY = "in-another-registry"
HAS_NO_FILE = "has-no-file"
_GROUP_FIELDS = (
    "relations",
    HAS_NO_MARKER,
    IN_ANOTHER_REGISTRY,
    HAS_NO_FILE,
    "why",
)
_SELECT = "select"
_LOCAL_FILE = re.compile(r"\./([^\s?#/][^\s?#]*)(\?)?(?:#(/\S*))?")
_REPO = r"//([^\s/?#]+/[^\s/?#]+/[^\s/?#]+)"
_REMOTE_FILE = re.compile(_REPO + r"/([^\s?#]+)(?:#(/\S*))?")
_REMOTE_REPO = re.compile(_REPO)


@final
@dataclass(frozen=True)
class FileRef:
    """A file a site is in that holds no marker: in this repository (repo None), or in the
    repository repo, `<git-host>/<owner>/<name>`, which keeps no group with it and which the
    lint doesn't read. An optional file
    (`?`) is only sometimes there, such as an untracked .env, so its absence isn't a problem.
    pointer is a JSON Pointer to the value in it."""

    repo: str | None
    path: str
    optional: bool
    pointer: str | None

    def text(self) -> str:
        where = "./" + self.path if self.repo is None else f"//{self.repo}/{self.path}"
        optional = "?" if self.optional else ""
        return where + optional + ("" if self.pointer is None else "#" + self.pointer)

    def unmarked(self) -> "FileRef":
        """The ref without its optional mark: what it refers to, however it's marked."""
        return replace(self, optional=False)


def parse_local(text: str) -> FileRef | None:
    """The file in this repository text refers to, or None if it isn't written as one."""
    match = _LOCAL_FILE.fullmatch(text)
    if match is None:
        return None
    return FileRef(None, match.group(1), match.group(2) is not None, match.group(3))


def parse_remote(text: str) -> FileRef | None:
    """The file in another repository text refers to, or None if it isn't written as one."""
    match = _REMOTE_FILE.fullmatch(text)
    if match is None:
        return None
    return FileRef(match.group(1), match.group(2), False, match.group(3))


def parse_file(text: str) -> FileRef | None:
    """The file, in this repository or another, text refers to, or None if it isn't written as
    one."""
    return parse_local(text) or parse_remote(text)


def parse_repo(text: str) -> str | None:
    """The repository, `<git-host>/<owner>/<name>`, text refers to, or None if it isn't written
    as one."""
    match = _REMOTE_REPO.fullmatch(text)
    return None if match is None else match.group(1)


@final
@dataclass(frozen=True)
class Group:
    """A group's table: its relations; each site with no marker here, by its label, as the field
    that says why: a file that holds no marker, in this repository or in another that keeps
    no such group; another repository that keeps the group and describes the site; or where a
    site in no file is set; the regex of each file that has one; and
    why its sites must change together, if it says. problems are what's wrong with the table,
    as messages saying how to fix it; definition is a fingerprint of what it states, which
    leaves out why and where each site with no file is set."""

    key: str
    relations: tuple[Relation, ...]
    local_files: tuple[tuple[str, FileRef], ...]
    remote_files: tuple[tuple[str, FileRef], ...]
    other_registries: tuple[tuple[str, str], ...]
    no_file_sites: tuple[tuple[str, str], ...]
    regexes: tuple[tuple[str, str], ...]
    why: str | None
    problems: tuple[str, ...]
    definition: str

    def regex(self, label: str) -> str | None:
        """The regex of the file labelled label, if it has one."""
        for name, regex in self.regexes:
            if name == label:
                return regex
        return None

    def unmarked_labels(self) -> list[tuple[str, str]]:
        """The label of each site the table gives one, with the field it's in, in order."""
        return (
            [(label, HAS_NO_MARKER) for label, _ in sorted(self.local_files + self.remote_files)]
            + [(label, IN_ANOTHER_REGISTRY) for label, _ in self.other_registries]
            + [(label, HAS_NO_FILE) for label, _ in self.no_file_sites]
        )


@final
@dataclass(frozen=True)
class ReviewedSite:
    """A site as the reviewed section records it: its marker (`COUPLED:<key>: <label>`), or a
    file's ref, with the unit on its value, the fingerprint of its block and its marker's
    regex, where recorded."""

    name: str
    unit: str | None
    block: str | None
    regex: str | None


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
    if _SELECT in table:
        problems.append(
            f"Drop `{_SELECT}`, and give each site its regex: a marked site after its marker's "
            "label, `COUPLED:<key>: <label> /<regex>/`, and a file in "
            f"`{HAS_NO_MARKER}` as `<label> = {{ file = \"<file>\", regex = '<regex>' }}`"
        )
    for field in sorted(table.keys() - {*_GROUP_FIELDS, _SELECT}):
        problems.append(f"Drop `{field}`: a group's table holds {', '.join(_GROUP_FIELDS)}")
    problems.extend(_order_problems(list(table)))
    relations: list[Relation] = []
    written = _strings(table.get("relations"), "relations", problems)
    if not written and "relations" not in table:
        problems.append('Give the group `relations = [...]`, such as `["proxy >= app"]`')
    for text in written:
        parsed = parse_relation(text)
        if isinstance(parsed, str):
            problems.append(parsed)
        else:
            relations.append(parsed)
    unmarked = _entries(table, HAS_NO_MARKER, _unmarked, _LOCAL_FORM, _file_advice, problems)
    files = tuple((label, ref) for label, (ref, _) in unmarked)
    regexes = tuple((label, regex) for label, (_, regex) in unmarked if regex is not None)
    other_registries = _entries(
        table, IN_ANOTHER_REGISTRY, _text(parse_repo), _REPO_FORM, _repo_advice, problems
    )
    no_file_sites = _entries(
        table, HAS_NO_FILE, _text(_where), _WHERE_FORM, _where_advice, problems
    )
    labels: dict[str, str] = {}
    for field, entries in (
        (HAS_NO_MARKER, files),
        (IN_ANOTHER_REGISTRY, other_registries),
        (HAS_NO_FILE, no_file_sites),
    ):
        for label, _ in entries:
            if label in labels:
                problems.append(
                    f"Give `{label}` one entry: it's in both `{labels[label]}` and `{field}`"
                )
            labels.setdefault(label, field)
    why = table.get("why")
    if not isinstance(why, str | None):
        problems.append("Write `why` as a string: why the sites must change together")
        why = None
    definition = _fingerprint(
        [*(f"relation {' '.join(text.split())}" for text in written)]
        + [
            f"{HAS_NO_MARKER} {label} {ref.text()}" + ("" if regex is None else f" /{regex}/")
            for label, (ref, regex) in unmarked
        ]
        + [f"{IN_ANOTHER_REGISTRY} {label} //{repo}" for label, repo in other_registries]
        + [f"{HAS_NO_FILE} {label}" for label, _ in no_file_sites]
    )
    return Group(
        key,
        tuple(relations),
        tuple((label, ref) for label, ref in files if ref.repo is None),
        tuple((label, ref) for label, ref in files if ref.repo is not None),
        other_registries,
        no_file_sites,
        regexes,
        why,
        tuple(problems),
        definition,
    )


def _order_problems(fields: list[str]) -> list[str]:
    """A problem naming the first of a table's fields, as written, that is out of _GROUP_FIELDS'
    order, and the field it must come before; none when they're in order. A dotted field takes
    its place from its first line, as TOML gives its keys in the order they first appear."""
    written = [field for field in fields if field in _GROUP_FIELDS]
    ordered = sorted(written, key=_GROUP_FIELDS.index)
    for found, expected in zip(written, ordered, strict=True):
        if found != expected:
            fields_in_order = ", ".join(_GROUP_FIELDS[:-1]) + f" and {_GROUP_FIELDS[-1]}"
            return [
                f"Put `{expected}` before `{found}`: a group's table gives "
                f"{fields_in_order}, in that order"
            ]
    return []


def _text[V](parse_value: Callable[[str], V | None]) -> Callable[[object], V | None]:
    """parse_value, for an entry that must be a string."""
    return lambda value: parse_value(value) if isinstance(value, str) else None


_FILE_TABLE_FIELDS = ("file", "regex")


def _unmarked(value: object) -> tuple[FileRef, str | None] | None:
    """The file an entry of has-no-marker gives, and its regex, if it has one, or None if it
    isn't written as `"<file>"` or `{ file = "<file>"[, regex = '<regex>'] }`."""
    if isinstance(value, str):
        ref = parse_file(value)
        return None if ref is None else (ref, None)
    if not isinstance(value, dict) or "file" not in value or set(value) - set(_FILE_TABLE_FIELDS):
        return None
    text, regex = value["file"], value.get("regex")
    if not isinstance(text, str) or not isinstance(regex, str | None):
        return None
    if regex is not None and _regex_error(regex) is not None:
        return None
    ref = parse_file(text)
    return None if ref is None else (ref, regex)


def _regex_error(regex: str) -> str | None:
    """Why regex isn't one, or None if it is."""
    if not regex:
        return "it's empty"
    try:
        re.compile(regex)
    except re.error as error:
        return str(error)
    return None


def _where(text: str) -> str | None:
    """Where a site with no file is set, or None if text doesn't say."""
    return text.strip() or None


_LOCAL_FORM = "./<path>[?][#<pointer>]"
_REMOTE_FORM = "//<git-host>/<owner>/<name>/<path>[#<pointer>]"
_REPO_FORM = "//<git-host>/<owner>/<name>"
_WHERE_FORM = "where it's set"


def _file_advice(label: str, value: object) -> str:
    table = f"`{label} = {{ file = \"./<path>[?]\", regex = '<regex>' }}`"
    if isinstance(value, dict):
        extra = sorted(set(value) - set(_FILE_TABLE_FIELDS))
        if extra:
            return (
                f"Drop `{extra[0]}` from `{label}` in `{HAS_NO_MARKER}`: a file's table holds "
                f"file and regex, {table}"
            )
        regex = value.get("regex")
        if isinstance(regex, str) and (error := _regex_error(regex)) is not None:
            return f"Fix the regex /{regex}/ for `{label}` in `{HAS_NO_MARKER}`: {error}"
        if "file" not in value:
            return f"Give `{label}` in `{HAS_NO_MARKER}` its file: {table}"
        if not isinstance(regex, str | None):
            return f"Write the regex for `{label}` in `{HAS_NO_MARKER}` as a string: {table}"
        file = value["file"]
        text = file if isinstance(file, str) else ""
    else:
        text = value if isinstance(value, str) else ""
    if text.startswith("//") and "?" in text:
        return (
            f"Drop the `?` from `{label}` in `{HAS_NO_MARKER}`: only a file in this "
            "repository can be only sometimes there"
        )
    return (
        f'Write `{label}` in `{HAS_NO_MARKER}` as `{label} = "{_LOCAL_FORM}"`, or for a '
        f'file in another repository, `{label} = "{_REMOTE_FORM}"`, or with a regex picking '
        f"its value out, as {table}"
    )


def _repo_advice(label: str, value: object) -> str:
    if isinstance(value, str) and parse_remote(value) is not None:
        return (
            f"Write `{label}` in `{IN_ANOTHER_REGISTRY}` as the repository alone, "
            f'`{label} = "{_REPO_FORM}"`, where `{label}` is a site of the group too; if that '
            f"repository keeps no such group, give `{label}` its file in `{HAS_NO_MARKER}`"
        )
    return f'Write `{label}` in `{IN_ANOTHER_REGISTRY}` as `{label} = "{_REPO_FORM}"`'


def _where_advice(label: str, _value: object) -> str:
    return f'Write `{label}` in `{HAS_NO_FILE}` as `{label} = "{_WHERE_FORM}"`'


def _entries[V](
    table: dict[str, object],
    field: str,
    parse_value: Callable[[object], V | None],
    form: str,
    advice: Callable[[str, object], str],
    problems: list[str],
) -> tuple[tuple[str, V], ...]:
    """Each site field gives a label to, with its value as parse_value reads it, in label
    order. form is how an entry is written, and advice says how to write one, given its label
    and value, when parse_value can't read it."""
    value = table.get(field, {})
    if not isinstance(value, dict):
        problems.append(f'Write `{field}` as a table by label: `{{ <label> = "{form}" }}`')
        return ()
    found: list[tuple[str, V]] = []
    for label, entry in sorted(value.items()):
        parsed = parse_value(entry)
        if LABEL.fullmatch(label) is None:
            problems.append(
                f"Name each site in `{field}` by a label, in lowercase letters and digits "
                f"joined by single hyphens: `{label}` isn't one"
            )
        elif parsed is None:
            problems.append(advice(label, entry))
        else:
            found.append((label, parsed))
    return tuple(found)


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
            unit, block, regex = fields.get("unit"), fields.get("block"), fields.get("regex")
            if not all(isinstance(value, str | None) for value in (unit, block, regex)):
                return broken
            sites.append(ReviewedSite(site, _optional(unit), _optional(block), _optional(regex)))
        reviewed[match.group(1)] = Reviewed(definition, tuple(sites))
    return reviewed, []


def _optional(value: object) -> str | None:
    return value if isinstance(value, str) else None


def with_reviewed(text: str, reviewed: dict[str, Reviewed]) -> str:
    """The registry text with its reviewed section written as reviewed: every line from the
    section's header, or its first table if the header is gone, is replaced."""
    lines = text.splitlines()
    cut = len(lines)
    for index, line in enumerate(lines):
        header = _header(line)
        if line.strip() == REVIEWED_HEADER or (header is not None and "reviewed" in header):
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
                for name, value in (
                    ("unit", site.unit),
                    ("block", site.block),
                    ("regex", site.regex),
                )
                if value is not None
            ]
            inline = "{ " + ", ".join(fields) + " }" if fields else "{}"
            rows.append(f"{json.dumps(site.name)} = {inline}")
        tables.append("\n".join(rows))
    return authored + "\n" + REVIEWED_HEADER + "\n\n" + "\n\n".join(tables) + "\n"


def entry_text(text: str, key: str) -> str | None:
    """The lines of key's table in the registry text, as written, or None if it has none. Its
    header may be written any way TOML allows, and it ends at the next header or the reviewed
    section's."""
    lines = text.splitlines()
    table = {f"COUPLED:{key}:": {}}
    start = next((n for n, line in enumerate(lines) if _header(line) == table), None)
    if start is None:
        return None
    end = start + 1
    while (
        end < len(lines) and _header(lines[end]) is None and lines[end].strip() != REVIEWED_HEADER
    ):
        end += 1
    return "\n".join(lines[start:end]).rstrip()


def _header(line: str) -> dict[str, object] | None:
    """What a line declares if it's a table header, as TOML reads it alone (`["COUPLED:a:"]` is
    `{"COUPLED:a:": {}}`), or None if it isn't one. TOML puts a header on a line of its own, so
    the parser reads it however it's quoted, spaced or commented. A line inside a multi-line
    string that reads as a header is taken for one."""
    if not line.lstrip().startswith("["):
        return None
    try:
        return tomllib.loads(line)
    except tomllib.TOMLDecodeError:
        return None


def _fingerprint(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()[:16]
