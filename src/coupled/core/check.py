"""Checking a repository's COUPLED groups: each marker's form, that every group has a table in
the registry, that its relations name its sites, and that the relations of a group using value,
set or text ops hold."""

from dataclasses import dataclass, replace
from typing import assert_never, final

from coupled.core.comments import Syntax, open_block_closer, syntax_of
from coupled.core.markers import End, Found, Malformed, Marker, Placed, find_markers
from coupled.core.registry import (
    HAS_NO_FILE,
    HAS_NO_MARKER,
    IN_ANOTHER_REGISTRY,
    FileRef,
    Group,
    Registry,
    Unparseable,
    table_name,
)
from coupled.core.relations import (
    Arith,
    Formula,
    Kind,
    MemberOp,
    Op,
    SetOp,
    TextOp,
    ValueOp,
    kind_of,
    value_side,
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
    compare_member,
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
            _with_closer_problem(item, lines[item.line], syntax),
            value_line(lines, item.line, syntax),
            tuple(block_lines(lines, item, placed, syntax)),
            item.close is not None,
            lines[item.line][item.stop :],
        )
        for item in placed
    ]


def _with_closer_problem(item: Placed, line: str, syntax: Syntax) -> Found:
    """The marker or END placed on line, with a problem if it's a marker in a block comment
    whose regex holds the comment's closer, which ends the comment there."""
    found = item.found
    if not isinstance(found, Marker) or found.regex is None:
        return found
    closer = open_block_closer(line[: item.start], syntax)
    if closer is None or closer not in f"/{found.regex}/":
        return found
    return replace(
        found,
        problems=(
            *found.problems,
            f"The regex holds `{closer}`, which closes the comment it's in. Write it so "
            f"`{closer}` doesn't appear, even across its slashes, such as `\\s*` as `\\s{{0,}}`",
        ),
    )


def regex_of(site: Site) -> str | None:
    """The regex the marker at site carries, if it carries one."""
    return site.found.regex if isinstance(site.found, Marker) else None


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
    paths = [ref.path for group in registry.groups.values() for _, ref in group.local_files]
    return list(dict.fromkeys(paths))


def unchecked(registry: Registry | Unparseable | None) -> list[str]:
    """The distinct other repositories the groups name, for a file or a site there, in order,
    which the lint doesn't read."""
    if not isinstance(registry, Registry):
        return []
    repos = [
        repo
        for group in registry.groups.values()
        for repo in [
            *(ref.repo for _, ref in group.remote_files if ref.repo is not None),
            *(repo for _, repo in group.other_registries),
        ]
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


_ONE_LINE_END = (
    "Drop the END closing this marker: its block is one line, which the marker describes "
    "without one"
)


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
        if isinstance(site.found, Marker) and site.closed and len(site.block) == 1:
            problems.append(Problem(site.where, _ONE_LINE_END))
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
        unmarked = self._group.unmarked_labels()
        for label, field in unmarked:
            if label in first:
                problems.append(
                    Problem(
                        self._where,
                        f"Drop `{label}` from `{field}`: {first[label]} marks it, so that's its "
                        "site",
                    )
                )
        elsewhere = "it's in another repository, which the lint doesn't read"
        unread = [(label, elsewhere) for label, _ in self._group.remote_files]
        for label, reason in sorted(unread):
            if self._group.regex(label) is not None:
                problems.append(
                    Problem(
                        self._where,
                        f"Drop the regex from `{label}` in `{HAS_NO_MARKER}`: {reason}",
                    )
                )
        for label, ref in self._group.local_files:
            if ref.pointer is not None and self._group.regex(label) is not None:
                problems.append(
                    Problem(
                        self._where,
                        f"Pick `{label}`'s value out with its #pointer or its regex, not both",
                    )
                )
        known = set(first) | {label for label, _ in unmarked}
        named = [
            label for relation in self._group.relations for label in (relation.left, relation.right)
        ]
        for label in dict.fromkeys(named):
            if label not in known:
                problems.append(
                    Problem(
                        self._where,
                        f"No site is labelled `{label}`. Mark it `COUPLED:{self._key}: "
                        f"{label}`, or if it can't hold a marker, give it the label in "
                        f"`{HAS_NO_MARKER}` or `{HAS_NO_FILE}`, or if it's a site in "
                        f"another repository that keeps this group, in `{IN_ANOTHER_REGISTRY}`; or "
                        "fix the label here",
                    )
                )
        return problems

    def _files_problems(self) -> list[Problem]:
        problems: list[Problem] = []
        for label, ref in self._group.local_files:
            if ref.path in self._marker_paths:
                problems.append(
                    Problem(
                        self._where,
                        f"`./{ref.path}` holds a marker of COUPLED:{self._key}:, so it can hold "
                        f"one: mark `{label}` there and drop it from `{HAS_NO_MARKER}`",
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
        if any(r.formula is not None and not isinstance(r.op, ValueOp) for r in relations):
            problems.append(f"Use a formula only with {' '.join(ValueOp)}")
        reads = f"{' '.join([*ValueOp, *SetOp, *MemberOp])}, which read values and members"
        regexes_unused = bool(kinds) and not {Kind.VALUE, Kind.SET}.intersection(kinds)
        if self._group.regexes and regexes_unused:
            problems.append(f"Use a regex in `{HAS_NO_MARKER}` only with {reads}")
        if kinds == [Kind.JUDGED] and not (self._group.why or "").strip():
            problems.append(
                f'Say why these sites are coupled, as `why = "..."`: the lint can\'t compare '
                f"what {ops[0]} relates, so `why` is all that tells a reviewer what must hold"
            )
        if kinds == [Kind.SET]:
            problems += self._read_both_ways()
        pairs: list[frozenset[str]] = []
        for relation in relations:
            if relation.formula is not None and (
                relation.formula.arith in (Arith.MUL, Arith.DIV) and relation.formula.operand == 0
            ):
                problems.append(f"Multiply or divide by a number other than 0: `{relation.text()}`")
            if relation.left == relation.right:
                problems.append(f"Relate `{relation.left}` to another site in `{relation.text()}`")
            elif frozenset((relation.left, relation.right)) in pairs:
                problems.append(
                    f"Relate `{relation.left}` and `{relation.right}` in only one relation"
                )
            pairs.append(frozenset((relation.left, relation.right)))
        result = [Problem(self._where, message) for message in problems]
        if regexes_unused:
            result += [
                Problem(site.where, f"Drop this marker's regex: use a regex only with {reads}")
                for site, _ in self._sites
                if regex_of(site) is not None
            ]
        marked = [label for _, label in self._sites]
        unmarked = [label for label, _ in self._group.unmarked_labels()]
        members = set(marked) | set(unmarked)
        if len(members) < 2:
            result.append(
                Problem(
                    self._where,
                    f"COUPLED:{self._key}: needs at least two sites, and has {len(members)}. "
                    "Mark or label the others, or if it's been removed, remove its table",
                )
            )
        related = {label for relation in relations for label in (relation.left, relation.right)}
        for site, label in self._sites:
            if label not in related:
                result.append(
                    Problem(
                        site.where,
                        f"Nothing relates this site: name `{label}` in a relation of "
                        f"{table_name(self._key)}",
                    )
                )
        for label, field in self._group.unmarked_labels():
            if label not in related and label not in marked:
                result.append(
                    Problem(
                        self._where,
                        f"Nothing relates `{label}`, in `{field}`: name it in a relation of "
                        f"{table_name(self._key)}",
                    )
                )
        return result

    def _read_both_ways(self) -> list[str]:
        """A problem for each site of a group of set ops that one relation reads as a value
        and another as a set."""
        as_value: dict[str, str] = {}
        as_set: dict[str, str] = {}
        for relation in self._group.relations:
            member = value_side(relation)
            for label in (relation.left, relation.right):
                reads = as_value if label == member else as_set
                reads.setdefault(label, relation.text())
        return [
            f"Read `{label}` as one value or as a set of names, not both: `{value}` reads it "
            f"as a value, and `{as_set[label]}` as a set"
            for label, value in as_value.items()
            if label in as_set
        ]

    def _value_labels(self) -> set[str]:
        """The labels of the sites the group reads as one value each."""
        kind = group_kind(self._group)
        if kind is Kind.VALUE:
            return {label for r in self._group.relations for label in (r.left, r.right)}
        return {label for r in self._group.relations if (label := value_side(r)) is not None}

    def _ends(self) -> list[Problem]:
        values = self._value_labels()
        why = (
            "relates values"
            if group_kind(self._group) is Kind.VALUE
            else "reads this site as one value"
        )
        return [
            Problem(
                site.where,
                f"Drop the END closing this marker: COUPLED:{self._key}: {why}, so its marker "
                "describes one line",
            )
            for site, label in self._sites
            if site.closed and len(site.block) > 1 and label in values
        ]

    def _values(self) -> list[Problem]:
        """The relations of a group using value ops."""
        readings, problems = self._read_values(self._value_labels())
        if problems:
            return problems
        for pair in self._pairs(readings, ValueOp):
            verdict = compare(pair.op, pair.mine.text, pair.other.text, pair.formula)
            problems += self._failure(pair.text, pair.where, pair.other_where, verdict, "values")
        return problems

    def _read_values(self, labels: set[str]) -> tuple[dict[str, tuple[str, Value]], list[Problem]]:
        """The value at each site and file with one of labels, with where it was read, and
        the problems with those that can't be read."""
        problems: list[Problem] = []
        readings: dict[str, tuple[str, Value]] = {}
        for site, label in self._sites:
            if label not in labels:
                continue
            if site.code is None:
                reading: Value | Unreadable = Unreadable(_NO_LINE)
            else:
                reading = read_value(site.code, regex_of(site))
            match reading:
                case Value():
                    readings[label] = (site.where, reading)
                case Unreadable(reason):
                    problems.append(
                        Problem(
                            site.where,
                            f"Can't read this site's value: {reason}. Pick it out with a "
                            f"regex after the marker's label, `COUPLED:{self._key}: {label} "
                            "/<regex>/`, or if the group's sites aren't single values, relate "
                            "them with a set, text or judged op",
                        )
                    )
                case _:
                    assert_never(reading)
        for label, ref, text in self._local_files():
            if label not in labels:
                continue
            reading = read_file_value(text, ref.pointer, self._group.regex(label)) or Unreadable(
                "it has more than one line: point at its value with #<pointer> if it's JSON, "
                f'or pick it out with a regex, `{label} = {{ file = "{ref.text()}", '
                "regex = '<regex>' }`"
            )
            match reading:
                case Value():
                    readings[label] = (ref.text(), reading)
                case Unreadable(reason):
                    problems.append(Problem(ref.text(), f"Can't read this file's value: {reason}"))
                case _:
                    assert_never(reading)
        return readings, problems

    def _members(self) -> list[Problem]:
        """The relations of a group using set ops, which read the member in a member-of or
        has-member relation as one value, and every other site as a set."""
        values = self._value_labels()
        values_read, problems = self._read_values(values)
        readings: dict[str, tuple[str, Members]] = {}
        for site, label in self._sites:
            if label in values:
                continue
            if not site.block:
                reading: Members | Unreadable = Unreadable(_NO_LINE)
            else:
                reading = read_members(site.block, regex_of(site))
            match reading:
                case Members():
                    readings[label] = (site.where, reading)
                case Unreadable(reason):
                    problems.append(
                        Problem(
                            site.where,
                            f"Can't read this site's members: {reason}. Pick each out with a "
                            f"regex after the marker's label, `COUPLED:{self._key}: {label} "
                            "/<regex>/`, or if they can't be picked out, relate the group's "
                            "sites with a judged op",
                        )
                    )
                case _:
                    assert_never(reading)
        for label, ref, text in self._local_files():
            if label in values:
                continue
            reading = read_file_members(text, ref.pointer, self._group.regex(label))
            match reading:
                case Members():
                    readings[label] = (ref.text(), reading)
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
            problems += self._failure(pair.text, pair.where, pair.other_where, verdict, "members")
        for relation in self._group.relations:
            member = value_side(relation)
            if member is None:
                continue
            members = relation.right if member == relation.left else relation.left
            value, held = values_read.get(member), readings.get(members)
            if value is None or held is None:
                continue
            where = {member: value[0], members: held[0]}
            problems += self._failure(
                relation.text(),
                where[relation.left],
                where[relation.right],
                compare_member(value[1], held[1]),
                "value or the members",
            )
        return problems

    def _texts(self) -> list[Problem]:
        """The relations of a group using the text op."""
        problems: list[Problem] = []
        readings: dict[str, tuple[str, Text]] = {}
        for site, label in self._sites:
            if site.block:
                readings[label] = (site.where, text_of(site.block))
            else:
                problems.append(Problem(site.where, f"Can't read this site's text: {_NO_LINE}"))
        for label, ref, text in self._local_files():
            reading = read_file_text(text, ref.pointer)
            match reading:
                case Text():
                    readings[label] = (ref.text(), reading)
                case Unreadable(reason):
                    problems.append(Problem(ref.text(), f"Can't read this file's text: {reason}"))
                case _:
                    assert_never(reading)
        if problems:
            return problems
        for pair in self._pairs(readings, TextOp):
            problems += self._failure(
                pair.text, pair.where, pair.other_where, compare_text(pair.mine, pair.other), "text"
            )
        return problems

    def _local_files(self) -> list[tuple[str, FileRef, str]]:
        """Each file in this repository the group gives a label, with its label and text. One
        that isn't there is left out: _files_problems reports it, unless it's optional."""
        found: list[tuple[str, FileRef, str]] = []
        for label, ref in self._group.local_files:
            file = self._files.get(ref.path)
            match file:
                case Content(text):
                    found.append((label, ref, text))
                case Missing() | None:
                    pass
                case _:
                    assert_never(file)
        return found

    def _pairs[T, O: Op](
        self, readings: dict[str, tuple[str, T]], family: type[O]
    ) -> list[_Pair[T, O]]:
        """Each two readings that a relation using an op of family compares, where both were
        read."""
        pairs: list[_Pair[T, O]] = []
        for relation in self._group.relations:
            op = relation.op
            if not isinstance(op, family):
                continue
            mine, other = readings.get(relation.left), readings.get(relation.right)
            if mine is not None and other is not None:
                pairs.append(_Pair(relation.text(), op, relation.formula, *mine, *other))
        return pairs

    def _failure(
        self, text: str, where: str, other_where: str, verdict: Verdict, things: str
    ) -> list[Problem]:
        """The problem with the relation text, between the readings at where and other_where,
        when it doesn't hold, things being what to change so that it does. It's reported at
        where."""
        match verdict:
            case Holds():
                return []
            case Fails(shown):
                why = self._group.why
                because = "" if why is None else f" They're coupled because {why.rstrip('.')}."
                return [
                    Problem(
                        where,
                        f"`{text}` doesn't hold with {other_where}: {shown}.{because} "
                        f"Change the {things} so it holds; change the relation only if what "
                        "must hold has changed",
                    )
                ]
            case Incomparable(reason):
                return [
                    Problem(
                        where,
                        f"Can't compare with {other_where} for `{text}`: {reason}",
                    )
                ]
            case _:
                assert_never(verdict)
