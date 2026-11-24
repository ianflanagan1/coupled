"""Checking a repository's COUPLED groups: each marker's form, that every group has a table in
the registry, that its relations name its sites and files, and that the relations of a group
using value ops hold."""

from dataclasses import dataclass
from typing import assert_never, final

from coupled.core.comments import syntax_of
from coupled.core.markers import End, Found, Malformed, Marker, find_markers
from coupled.core.registry import Group, Registry, Unparseable, table_name
from coupled.core.relations import (
    Arith,
    Bare,
    Equation,
    FileRef,
    Formula,
    Label,
    Ref,
    StructuralOp,
    ValueOp,
    ref_text,
    refs,
)
from coupled.core.rewrite import Wanted, wanted, written_after
from coupled.core.settings import TagMessage
from coupled.core.values import (
    Fails,
    Holds,
    Incomparable,
    Reading,
    Unreadable,
    Value,
    block_lines,
    compare,
    read_file_value,
    read_value,
    value_line,
)


@final
@dataclass(frozen=True)
class Site:
    """A marker or END found in this repository, at where (`path:line`), with the code of the
    line it describes, or None if there's no such line, the lines of the block it describes,
    whether an END closes it, and the text on its line after it."""

    where: str
    found: Found
    code: str | None
    block: tuple[str, ...]
    closed: bool
    after: str


def file_sites(path: str, lines: list[str]) -> list[Site]:
    """A site for each marker and END in the lines of the file at path."""
    placed = find_markers(lines)
    syntax = syntax_of(path)
    return [
        Site(
            f"{path}:{item.line + 1}",
            item.found,
            value_line(lines, item.line, syntax),
            tuple(block_lines(lines, item, placed, syntax)),
            item.close is not None,
            lines[item.line][item.stop :],
        )
        for item in placed
    ]


@final
@dataclass(frozen=True)
class Content:
    """A file a group refers to, read."""

    text: str


@final
@dataclass(frozen=True)
class Missing:
    """A file a group refers to that isn't there."""


type FileRead = Content | Missing


@final
@dataclass(frozen=True)
class Problem:
    where: str
    message: str


def labelled(sites: list[Site], key: str) -> list[tuple[Site, str]]:
    """key's labelled markers, with their labels, in the order found."""
    return [
        (site, site.found.label)
        for site in sites
        if isinstance(site.found, Marker) and site.found.key == key and site.found.label is not None
    ]


def file_paths(registry: Registry) -> list[str]:
    """The distinct paths in this repository that the registry's groups refer to, in order:
    the files check needs read."""
    paths: list[str] = []
    for group in registry.groups.values():
        paths += [
            ref.path for ref in group.file_refs() if ref.repo is None and ref.path not in paths
        ]
    return paths


def unchecked(registry: Registry | Unparseable | None) -> list[str]:
    """The distinct repositories the groups refer to files in, in order, which the lint doesn't
    read."""
    if not isinstance(registry, Registry):
        return []
    repos: list[str] = []
    for group in registry.groups.values():
        repos += [
            ref.repo for ref in group.file_refs() if ref.repo is not None and ref.repo not in repos
        ]
    return repos


def is_value_group(group: Group) -> bool:
    ops = [relation.op for relation in group.relations]
    return bool(ops) and not any(isinstance(op, StructuralOp) for op in ops)


def check(
    sites: list[Site],
    registry: Registry | Unparseable | None,
    files: dict[str, FileRead],
    registry_file: str,
    message: TagMessage,
) -> list[Problem]:
    """The problems with sites and the registry at registry_file, given each file in this
    repository that its groups refer to (see file_paths), and what the settings say follows each
    marker's label. Other repositories aren't read."""
    problems = _site_problems(sites)
    problems += _message_problems(sites, wanted(markers(sites), registry, message, registry_file))
    keys: list[str] = []
    for site in sites:
        if isinstance(site.found, Marker) and site.found.key not in keys:
            keys.append(site.found.key)
    match registry:
        case None:
            if keys:
                problems.append(
                    Problem(
                        registry_file,
                        f"There's no registry. Add {registry_file}, with `version = 1` and a "
                        f"table for each group, such as {table_name(keys[0])}",
                    )
                )
            return problems
        case Unparseable(reason):
            return problems + [Problem(registry_file, f"Can't read the registry: {reason}")]
        case Registry():
            pass
        case _:
            assert_never(registry)
    problems += [Problem(registry_file, message) for message in registry.problems]
    for key in keys:
        if key not in registry.groups:
            first = next(s for s in sites if isinstance(s.found, Marker) and s.found.key == key)
            problems.append(
                Problem(
                    first.where,
                    f"Add {table_name(key)} to {registry_file}, with the group's relations",
                )
            )
    for group in registry.groups.values():
        problems += _GroupCheck(group, sites, files, registry_file).problems()
    return problems


def _site_problems(sites: list[Site]) -> list[Problem]:
    """The problems with markers and ENDs on their own."""
    problems: list[Problem] = []
    for site in sites:
        match site.found:
            case Malformed(problem):
                problems.append(Problem(site.where, problem))
            case End(_, messages) | Marker(problems=messages):
                problems += [Problem(site.where, message) for message in messages]
            case _:
                assert_never(site.found)
        if isinstance(site.found, Marker) and site.code is None:
            problems.append(
                Problem(
                    site.where,
                    "Put the code this marker describes on its line, or on the line after it, "
                    "with no blank line between",
                )
            )
    return problems


def markers(sites: list[Site]) -> list[tuple[str, str]]:
    """The key and label of each labelled marker in sites, in order."""
    return [
        (site.found.key, site.found.label)
        for site in sites
        if isinstance(site.found, Marker) and site.found.label is not None
    ]


def _message_problems(sites: list[Site], messages: Wanted) -> list[Problem]:
    problems: list[Problem] = []
    for site in sites:
        if not isinstance(site.found, Marker) or site.found.label is None:
            continue
        message = messages.get((site.found.key, site.found.label))
        if written_after(site.after, message) is None:
            continue
        if message is None:
            text = "Drop the message after this marker's label, as the settings give it none"
        else:
            text = f"Write the message after this marker's label as `. {message}`"
        problems.append(Problem(site.where, f"{text}; --fix does it"))
    return problems


_NO_LINE = "the marker describes no line"


@final
class _GroupCheck:
    def __init__(
        self,
        group: Group,
        sites: list[Site],
        files: dict[str, FileRead],
        registry_file: str,
    ) -> None:
        self._group = group
        self._key = group.key
        self._files = files
        self._sites = labelled(sites, group.key)
        self._marker_paths = {
            site.where.rsplit(":", 1)[0]
            for site in sites
            if isinstance(site.found, Marker) and site.found.key == group.key
        }
        self._where = f"{registry_file} {table_name(group.key)}"

    def problems(self) -> list[Problem]:
        problems = [Problem(self._where, message) for message in self._group.problems]
        problems += self._labels() + self._files_problems() + self._relations_problems()
        problems += self._ends()
        if problems or not is_value_group(self._group):
            return problems
        return self._values()

    def _labels(self) -> list[Problem]:
        problems: list[Problem] = []
        first: dict[str, str] = {}
        for site, label in self._sites:
            if label in first:
                problems.append(
                    Problem(
                        site.where,
                        f"Another site of COUPLED:{self._key}: is labelled `{label}`, at "
                        f"{first[label]}: give each site its own label",
                    )
                )
            else:
                first[label] = site.where
        named = [
            ref.text
            for relation in self._group.relations
            for ref in refs(relation)
            if isinstance(ref, Label)
        ] + [label for label, _ in self._group.selectors]
        reported: list[str] = []
        for label in named:
            if label not in first and label not in reported:
                reported.append(label)
                problems.append(
                    Problem(
                        self._where,
                        f"No site is labelled `{label}`. Mark it `COUPLED:{self._key}: "
                        f"{label}`, or fix the label here",
                    )
                )
        return problems

    def _files_problems(self) -> list[Problem]:
        problems: list[Problem] = []
        for ref in self._group.file_refs():
            if ref.repo is not None:
                continue
            if ref.path in self._marker_paths:
                problems.append(
                    Problem(
                        self._where,
                        f"Name the site in `./{ref.path}` by its marker's label, not as a file",
                    )
                )
            elif not ref.optional and isinstance(self._files.get(ref.path), Missing):
                problems.append(
                    Problem(
                        ref.text(),
                        f"COUPLED:{self._key}: names this file, but it isn't there. Fix the "
                        "path, or if the file is only sometimes there, such as an untracked "
                        ".env, mark it optional: ./<path>?",
                    )
                )
        return problems

    def _relations_problems(self) -> list[Problem]:
        relations = self._group.relations
        problems: list[str] = []
        ops = [relation.op for relation in relations]
        value = [op for op in ops if isinstance(op, ValueOp)]
        structural = [op for op in ops if isinstance(op, StructuralOp)]
        if value and structural:
            problems.append(
                f"Use either value ops or structural ops in a group, not {value[0]} and "
                f"{structural[0]}: split it into two keys"
            )
        bare = [relation for relation in relations if isinstance(relation, Bare)]
        if bare and len(relations) > 1:
            problems.append(f"Write a bare {bare[0].op} as the group's only relation")
        equations = [relation for relation in relations if isinstance(relation, Equation)]
        if structural and (
            self._group.selectors or any(eq.formula is not None for eq in equations)
        ):
            problems.append(f"Use a formula or `select` only with {' '.join(ValueOp)}")
        pairs: list[frozenset[Ref]] = []
        for equation in equations:
            if equation.formula is not None and (
                equation.formula.arith in (Arith.MUL, Arith.DIV) and equation.formula.operand == 0
            ):
                problems.append(f"Multiply or divide by a number other than 0: `{equation.text()}`")
            left, right = _plain(equation.left), _plain(equation.right)
            if left == right:
                problems.append(
                    f"Relate `{ref_text(left)}` to another site or file in `{equation.text()}`"
                )
            elif frozenset((left, right)) in pairs:
                problems.append(
                    f"Relate `{ref_text(left)}` and `{ref_text(right)}` in only one relation"
                )
            pairs.append(frozenset((left, right)))
        result = [Problem(self._where, message) for message in problems]
        members = [Label(label) for _, label in self._sites] + [
            ref.unmarked() for ref in self._group.file_refs()
        ]
        if len(members) < 2:
            result.append(
                Problem(
                    self._where,
                    f"COUPLED:{self._key}: needs at least two sites or files, and has "
                    f"{len(members)}. Mark or list the others, or if it's been removed, remove "
                    "its table",
                )
            )
        if bare:
            return result
        related = {_plain(ref) for equation in equations for ref in refs(equation)}
        for site, label in self._sites:
            if Label(label) not in related:
                result.append(
                    Problem(
                        site.where,
                        f"Nothing relates this site: name `{label}` in a relation of "
                        f"{table_name(self._key)}",
                    )
                )
        for ref in self._group.files:
            if ref.unmarked() not in related:
                result.append(
                    Problem(
                        self._where,
                        f"Nothing relates `{ref.text()}`: name it in a relation, or for a group "
                        "whose sites are all the same, make its relation a bare op",
                    )
                )
        return result

    def _ends(self) -> list[Problem]:
        if not is_value_group(self._group):
            return []
        return [
            Problem(
                site.where,
                f"Drop the END closing this marker: COUPLED:{self._key}: relates values, so "
                "each marker describes one line",
            )
            for site, _ in self._sites
            if site.closed
        ]

    def _values(self) -> list[Problem]:
        """The relations of a group using value ops."""
        problems: list[Problem] = []
        readings: dict[Ref, tuple[str, Reading]] = {}
        for site, label in self._sites:
            if site.code is None:
                reading: Reading = Unreadable(_NO_LINE)
            else:
                reading = read_value(site.code, self._group.selector(label))
            if isinstance(reading, Unreadable):
                problems.append(
                    Problem(
                        site.where,
                        f"Can't read this site's value: {reading.reason}. Pick it out with "
                        f"`select = {{ {label} = '<regex>' }}`, or if the group isn't single "
                        "values, use a structural op",
                    )
                )
            readings[Label(label)] = (site.where, reading)
        for ref in self._group.file_refs():
            if ref.repo is not None:
                continue
            file = self._files.get(ref.path)
            match file:
                case Content(text):
                    reading = read_file_value(text, ref.pointer) or Unreadable(
                        "it has more than one line: point at its value with #<pointer>, if "
                        "it's JSON"
                    )
                    if isinstance(reading, Unreadable):
                        problems.append(
                            Problem(ref.text(), f"Can't read this file's value: {reading.reason}")
                        )
                    readings[ref.unmarked()] = (ref.text(), reading)
                case Missing() | None:
                    pass  # Reported by _files_problems, unless it's optional.
                case _:
                    assert_never(file)
        if problems:
            return problems
        for relation in self._group.relations:
            match relation:
                case Equation(left=left, op=op, right=right, formula=formula):
                    assert isinstance(op, ValueOp)
                    mine, other = readings.get(_plain(left)), readings.get(_plain(right))
                    if mine is not None and other is not None:
                        problems += _relation(
                            relation.text(), op, formula, mine, other, self._group.why
                        )
                case Bare():
                    every = list(readings.values())
                    for reading in every[1:]:
                        problems += _relation(
                            "=", ValueOp.EQ, None, reading, every[0], self._group.why
                        )
                case _:
                    assert_never(relation)
        return problems


def _plain(ref: Ref) -> Ref:
    return ref.unmarked() if isinstance(ref, FileRef) else ref


def _relation(
    text: str,
    op: ValueOp,
    formula: Formula | None,
    mine: tuple[str, Reading],
    other: tuple[str, Reading],
    why: str | None,
) -> list[Problem]:
    (where, reading), (other_where, other_reading) = mine, other
    assert isinstance(reading, Value) and isinstance(other_reading, Value)
    match compare(op, reading.text, other_reading.text, formula):
        case Holds():
            return []
        case Fails(shown):
            because = "" if why is None else f" They're coupled because {why.rstrip('.')}."
            return [
                Problem(
                    where,
                    f"`{text}` doesn't hold with {other_where}: {shown}.{because} Change the "
                    "values so it holds; change the relation only if what must hold has changed",
                )
            ]
        case Incomparable(reason):
            return [Problem(where, f"Can't compare with {other_where} for `{text}`: {reason}")]
