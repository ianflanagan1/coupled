"""Checking a repository's COUPLED groups: each marker's form, that every group has a table in
the registry, that its relations name its sites and files, and that the relations of a group
using value, set or text ops hold."""

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
    Kind,
    Label,
    Op,
    Ref,
    SetOp,
    TextOp,
    ValueOp,
    kind_of,
    ref_text,
    refs,
)
from coupled.core.rewrite import Wanted, wanted, written_after
from coupled.core.settings import MarkerMessage
from coupled.core.values import (
    Fails,
    Holds,
    Incomparable,
    Members,
    Text,
    Unreadable,
    Value,
    Verdict,
    block_lines,
    compare,
    compare_members,
    compare_text,
    read_file_members,
    read_file_text,
    read_file_value,
    read_members,
    read_value,
    text_of,
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
    paths = [
        ref.path
        for group in registry.groups.values()
        for ref in group.file_refs()
        if ref.repo is None
    ]
    return list(dict.fromkeys(paths))


def unchecked(registry: Registry | Unparseable | None) -> list[str]:
    """The distinct repositories the groups refer to files in, in order, which the lint doesn't
    read."""
    if not isinstance(registry, Registry):
        return []
    repos = [
        ref.repo
        for group in registry.groups.values()
        for ref in group.file_refs()
        if ref.repo is not None
    ]
    return list(dict.fromkeys(repos))


def no_file_sites(registry: Registry | Unparseable | None) -> list[str]:
    """Each site of the groups that has no file, as `<key> <label>`, in order: sites the lint
    can't read, such as settings made in a cloud console."""
    if not isinstance(registry, Registry):
        return []
    return [
        f"{group.key} {label}"
        for group in registry.groups.values()
        for label, _ in group.no_file_sites
    ]


def group_kind(group: Group) -> Kind | None:
    """The kind of op the group's relations use, or None if it has no relations or mixes
    kinds."""
    kinds = {kind_of(relation.op) for relation in group.relations}
    return next(iter(kinds)) if len(kinds) == 1 else None


def check(
    sites: list[Site],
    registry: Registry | Unparseable | None,
    files: dict[str, FileRead],
    registry_file: str,
    message: MarkerMessage,
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
@dataclass(frozen=True)
class _Pair[T, O: Op]:
    """Two readings a relation compares: the relation as written, its op and formula, and each
    reading with where it was read. The first is where a failure is reported."""

    text: str
    op: O
    formula: Formula | None
    where: str
    mine: T
    other_where: str
    other: T


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
        if problems:
            return problems
        kind = group_kind(self._group)
        match kind:
            case Kind.VALUE:
                return self._values()
            case Kind.SET:
                return self._members()
            case Kind.TEXT:
                return self._texts()
            case Kind.JUDGED | None:
                return []
            case _:
                assert_never(kind)

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
        no_file = [label for label, _ in self._group.no_file_sites]
        for label in no_file:
            if label in first:
                problems.append(
                    Problem(
                        self._where,
                        f"Drop `{label}` from `has-no-file`: {first[label]} marks it, so that's "
                        "its site",
                    )
                )
            elif self._group.selector(label) is not None:
                problems.append(
                    Problem(
                        self._where,
                        f"Drop `{label}` from `select`: it has no file for the lint to read",
                    )
                )
        reported: list[str] = [*no_file]
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
        kinds = list(dict.fromkeys(kind_of(op) for op in ops))
        if len(kinds) > 1:
            other = next(op for op in ops if kind_of(op) != kinds[0])
            problems.append(
                f"Use ops of one kind in a group, not {ops[0]} and {other}: split it into two keys"
            )
        bare = [relation for relation in relations if isinstance(relation, Bare)]
        if bare and len(relations) > 1:
            problems.append(f"Write a bare {bare[0].op} as the group's only relation")
        equations = [relation for relation in relations if isinstance(relation, Equation)]
        if any(eq.formula is not None and not isinstance(eq.op, ValueOp) for eq in equations):
            problems.append(f"Use a formula only with {' '.join(ValueOp)}")
        if self._group.selectors and kinds and not {Kind.VALUE, Kind.SET}.intersection(kinds):
            problems.append(f"Use `select` only with {' '.join([*ValueOp, *SetOp])}")
        if kinds == [Kind.JUDGED] and not (self._group.why or "").strip():
            problems.append(
                f'Say why these sites are coupled, as `why = "..."`: the lint can\'t compare '
                f"what {ops[0]} relates, so `why` is all that tells a reviewer what must hold"
            )
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
        members = (
            [Label(label) for _, label in self._sites]
            + [ref.unmarked() for ref in self._group.file_refs()]
            + [Label(label) for label, _ in self._group.no_file_sites]
        )
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
        marked = [label for _, label in self._sites]
        for label, _ in self._group.no_file_sites:
            if Label(label) not in related and label not in marked:
                result.append(
                    Problem(
                        self._where,
                        f"Nothing relates `{label}`, which has no file: name it in a relation of "
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
        if group_kind(self._group) is not Kind.VALUE:
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
        readings: dict[Ref, tuple[str, Value]] = {}
        for site, label in self._sites:
            if site.code is None:
                reading: Value | Unreadable = Unreadable(_NO_LINE)
            else:
                reading = read_value(site.code, self._group.selector(label))
            match reading:
                case Value():
                    readings[Label(label)] = (site.where, reading)
                case Unreadable(reason):
                    problems.append(
                        Problem(
                            site.where,
                            f"Can't read this site's value: {reason}. Pick it out with "
                            f"`select = {{ {label} = '<regex>' }}`, or if the group's sites "
                            "aren't single values, relate them with a set, text or judged op",
                        )
                    )
                case _:
                    assert_never(reading)
        for ref, text in self._local_files():
            reading = read_file_value(text, ref.pointer) or Unreadable(
                "it has more than one line: point at its value with #<pointer>, if it's JSON"
            )
            match reading:
                case Value():
                    readings[ref.unmarked()] = (ref.text(), reading)
                case Unreadable(reason):
                    problems.append(Problem(ref.text(), f"Can't read this file's value: {reason}"))
                case _:
                    assert_never(reading)
        if problems:
            return problems
        for pair in self._pairs(readings, ValueOp):
            verdict = compare(pair.op, pair.mine.text, pair.other.text, pair.formula)
            problems += self._failure(pair, verdict, "values")
        return problems

    def _members(self) -> list[Problem]:
        """The relations of a group using set ops."""
        problems: list[Problem] = []
        readings: dict[Ref, tuple[str, Members]] = {}
        for site, label in self._sites:
            if not site.block:
                reading: Members | Unreadable = Unreadable(_NO_LINE)
            else:
                reading = read_members(site.block, self._group.selector(label))
            match reading:
                case Members():
                    readings[Label(label)] = (site.where, reading)
                case Unreadable(reason):
                    problems.append(
                        Problem(
                            site.where,
                            f"Can't read this site's members: {reason}. Pick each out with "
                            f"`select = {{ {label} = '<regex>' }}`, or if they can't be picked "
                            "out, relate the group's sites with a judged op",
                        )
                    )
                case _:
                    assert_never(reading)
        for ref, text in self._local_files():
            reading = read_file_members(text, ref.pointer)
            match reading:
                case Members():
                    readings[ref.unmarked()] = (ref.text(), reading)
                case Unreadable(reason):
                    problems.append(
                        Problem(ref.text(), f"Can't read this file's members: {reason}")
                    )
                case _:
                    assert_never(reading)
        if problems:
            return problems
        for pair in self._pairs(readings, SetOp):
            verdict = compare_members(pair.op, pair.mine, pair.other)
            problems += self._failure(pair, verdict, "members")
        return problems

    def _texts(self) -> list[Problem]:
        """The relations of a group using the text op."""
        problems: list[Problem] = []
        readings: dict[Ref, tuple[str, Text]] = {}
        for site, label in self._sites:
            if site.block:
                readings[Label(label)] = (site.where, text_of(site.block))
            else:
                problems.append(Problem(site.where, f"Can't read this site's text: {_NO_LINE}"))
        for ref, text in self._local_files():
            reading = read_file_text(text, ref.pointer)
            match reading:
                case Text():
                    readings[ref.unmarked()] = (ref.text(), reading)
                case Unreadable(reason):
                    problems.append(Problem(ref.text(), f"Can't read this file's text: {reason}"))
                case _:
                    assert_never(reading)
        if problems:
            return problems
        for pair in self._pairs(readings, TextOp):
            problems += self._failure(pair, compare_text(pair.mine, pair.other), "text")
        return problems

    def _local_files(self) -> list[tuple[FileRef, str]]:
        """Each file in this repository the group refers to, with its text. One that isn't
        there is left out: _files_problems reports it, unless it's optional."""
        found: list[tuple[FileRef, str]] = []
        for ref in self._group.file_refs():
            if ref.repo is not None:
                continue
            file = self._files.get(ref.path)
            match file:
                case Content(text):
                    found.append((ref, text))
                case Missing() | None:
                    pass
                case _:
                    assert_never(file)
        return found

    def _pairs[T, O: Op](
        self, readings: dict[Ref, tuple[str, T]], family: type[O]
    ) -> list[_Pair[T, O]]:
        """Each two readings that a relation using an op of family compares: an equation's two
        refs, where both were read, or for a bare op, each reading with the first."""
        pairs: list[_Pair[T, O]] = []
        for relation in self._group.relations:
            op = relation.op
            if not isinstance(op, family):
                continue
            match relation:
                case Equation(left=left, right=right, formula=formula):
                    mine, other = readings.get(_plain(left)), readings.get(_plain(right))
                    if mine is not None and other is not None:
                        pairs.append(_Pair(relation.text(), op, formula, *mine, *other))
                case Bare():
                    every = list(readings.values())
                    pairs += [_Pair(str(op), op, None, *each, *every[0]) for each in every[1:]]
                case _:
                    assert_never(relation)
        return pairs

    def _failure[T, O: Op](self, pair: _Pair[T, O], verdict: Verdict, things: str) -> list[Problem]:
        """The problem with a pair whose relation doesn't hold, things being what to change so
        that it does."""
        match verdict:
            case Holds():
                return []
            case Fails(shown):
                why = self._group.why
                because = "" if why is None else f" They're coupled because {why.rstrip('.')}."
                return [
                    Problem(
                        pair.where,
                        f"`{pair.text}` doesn't hold with {pair.other_where}: {shown}.{because} "
                        f"Change the {things} so it holds; change the relation only if what "
                        "must hold has changed",
                    )
                ]
            case Incomparable(reason):
                return [
                    Problem(
                        pair.where,
                        f"Can't compare with {pair.other_where} for `{pair.text}`: {reason}",
                    )
                ]
            case _:
                assert_never(verdict)


def _plain(ref: Ref) -> Ref:
    return ref.unmarked() if isinstance(ref, FileRef) else ref
