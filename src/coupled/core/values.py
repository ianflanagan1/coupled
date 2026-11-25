"""Reading what a marker describes, as a group's ops need it, and comparing two of them: a
single value under an op and formula, the names in a block as a set, a value with a set, or a
block's text."""

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import assert_never, final

from coupled.core.comments import Syntax, is_comment_line, strip_comment
from coupled.core.markers import Placed
from coupled.core.relations import Arith, Formula, SetOp, ValueOp


@final
@dataclass(frozen=True)
class Value:
    text: str


@final
@dataclass(frozen=True)
class Unreadable:
    """No single value could be read, and why."""

    reason: str


type Reading = Value | Unreadable


@final
@dataclass(frozen=True)
class Members:
    """The distinct names read at a site or in a file, in the order found."""

    names: tuple[str, ...]


@final
@dataclass(frozen=True)
class Text:
    """The text at a site or in a file: its lines, each without the whitespace around it, and
    without the blank ones, so that its indentation isn't part of it."""

    lines: tuple[str, ...]


_QUOTED = re.compile(r"'([^']*)'|\"([^\"]*)\"|`([^`]*)`")
_IMAGE = re.compile(r"(?:^\s*FROM\s+(?:--\S+\s+)*|\bimage:\s*)[^\s:]+:v?(\d+(?:\.\d+)*)")
_ASSIGNMENT = re.compile(r"^\s*(?:[\w$]+\s+)*?[\w.$-]+\s*[=:]\s*([^\s;,]+)\s*[;,]?\s*\\?$")
_DIRECTIVE = re.compile(r"^\s*[\w.-]+(?:\s+[~^=*]+)?\s+([^\s;{]+)\s*[;{]?\s*$")

_VERSION = re.compile(r"v?(\d+(?:\.\d+)*)")
_NUMBER = re.compile(r"(-?\d[\d_]*(?:\.\d+)?)\s*[A-Za-z%]*")
_UNIT = re.compile(r"-?\d[\d_]*(?:\.\d+)?\s*([A-Za-z%]*)")


def value_line(lines: list[str], index: int, syntax: Syntax) -> str | None:
    """The code of the line a marker on lines[index] describes, without its comment, comments
    being in syntax: the marker's own line's code before its comment, or if it has none, the
    first line after it that isn't a comment. None if there's no such line, or a blank line
    comes first."""
    described = described_line(lines, index, syntax)
    if described is None:
        return None
    line = _head(lines[index]) if described == index else lines[described]
    return strip_comment(line, syntax).strip()


def _head(line: str) -> str:
    """line up to the marker on it."""
    return line[: line.find("COUPLED:")] if "COUPLED:" in line else line


def described_line(lines: list[str], index: int, syntax: Syntax) -> int | None:
    """The index of the line a marker on lines[index] describes, comments being in syntax: its
    own line if it has code before the marker's comment, or else the first line after it that
    isn't a comment. None if there's no such line, or a blank line comes first."""
    if strip_comment(_head(lines[index]), syntax).strip():
        return index
    for after in range(index + 1, len(lines)):
        if not lines[after].strip():
            return None
        if not is_comment_line(lines[after], syntax):
            return after
    return None


def block_lines(
    lines: list[str], marker: Placed, placed: list[Placed], syntax: Syntax
) -> list[str]:
    """The lines of code a marker describes, comments being in syntax, each stripped, without
    blank lines: the line value_line gives, then, if an END closes the marker, the lines down
    to the END. The markers of blocks inside it, placed being every marker in lines, are left
    out of it, so rewording them doesn't change it. Empty if the marker describes no line, or
    its END comes first."""
    first = described_line(lines, marker.line, syntax)
    if first is None or (marker.close is not None and first > marker.close):
        return []
    code = value_line(lines, marker.line, syntax) if first == marker.line else lines[first].strip()
    assert code is not None
    if marker.close is None:
        return [code]
    starts = {other.line for other in placed if first < other.line < marker.close}
    block = [code]
    for index in range(first + 1, marker.close):
        line = strip_comment(_head(lines[index]), syntax) if index in starts else lines[index]
        if line.strip():
            block.append(line.strip())
    return block


def read_value(code: str, regex: str | None) -> Reading:
    """The value in a line of code: what the regex matches (its capture group, if it has
    one), or else the one quoted literal, image tag, assignment or directive value on it."""
    if regex is not None:
        match = re.search(regex, code)
        if match is None:
            return Unreadable(f"the regex /{regex}/ doesn't match `{code}`")
        return Value(match.group(1) if match.re.groups else match.group())
    quoted = _QUOTED.findall(code)
    if len(quoted) == 1:
        return Value("".join(quoted[0]))
    if len(quoted) > 1:
        return Unreadable(f"`{code}` has several quoted values")
    for pattern in (_IMAGE, _ASSIGNMENT, _DIRECTIVE):
        if (match := pattern.search(code)) is not None:
            return Value(match.group(1))
    return Unreadable(f"`{code}` has no single value")


def read_file_value(content: str, pointer: str | None, regex: str | None) -> Reading | None:
    """The value in a file a group refers to: what the regex first matches in it (its
    capture group, if it has one), with `^` and `$` matching at each line; or at the JSON
    Pointer; or if there's neither, the whole file when it's one line. None when there's neither
    and the file is longer."""
    if regex is not None:
        match = re.search(regex, content, re.MULTILINE)
        if match is None:
            return Unreadable(f"the regex /{regex}/ matches nothing in it")
        return Value(match.group(1) if match.re.groups else match.group())
    if pointer is None:
        lines = content.strip().splitlines()
        return Value(lines[0].strip()) if len(lines) == 1 else None
    try:
        node = json.loads(content)
    except json.JSONDecodeError:
        return Unreadable("it isn't JSON, so a #<pointer> can't reach into it")
    at = _resolve(node, pointer)
    if at is None:
        return Unreadable(f"it has nothing at #{pointer}")
    if not _is_scalar(at.node):
        return Unreadable(f"#{pointer} isn't a string or number")
    return Value(str(at.node))


def read_members(block: tuple[str, ...], regex: str | None) -> Members | Unreadable:
    """The names in the lines of a block: every match of the regex (its capture group, if it
    has one), or with no regex, every quoted literal."""
    names: list[str] = []
    for line in block:
        if regex is None:
            names += ["".join(quoted) for quoted in _QUOTED.findall(line)]
        else:
            names += [
                match.group(1) if match.re.groups else match.group()
                for match in re.finditer(regex, line)
            ]
    if names:
        return Members(tuple(dict.fromkeys(names)))
    if regex is None:
        return Unreadable("its lines hold no quoted values")
    return Unreadable(f"the regex /{regex}/ matches nothing in its lines")


def read_file_members(content: str, pointer: str | None, regex: str | None) -> Members | Unreadable:
    """The names in a file a group refers to: every match of the regex in its lines; or at
    the JSON Pointer, a list's items or an object's keys; or if there's neither, its lines."""
    if regex is not None:
        return read_members(tuple(content.splitlines()), regex)
    if pointer is None:
        return Members(tuple(dict.fromkeys(text_of(content.splitlines()).lines)))
    try:
        node = json.loads(content)
    except json.JSONDecodeError:
        return Unreadable("it isn't JSON, so a #<pointer> can't reach into it")
    at = _resolve(node, pointer)
    if at is None:
        return Unreadable(f"it has nothing at #{pointer}")
    if isinstance(at.node, dict):
        return Members(tuple(str(key) for key in at.node))
    if isinstance(at.node, list) and all(_is_scalar(item) for item in at.node):
        return Members(tuple(dict.fromkeys(str(item) for item in at.node)))
    return Unreadable(f"#{pointer} isn't a list of strings or numbers, or an object")


def text_of(lines: Iterable[str]) -> Text:
    return Text(tuple(line.strip() for line in lines if line.strip()))


def read_file_text(content: str, pointer: str | None) -> Text | Unreadable:
    """The text of a file a group refers to: all of it, or the JSON at the pointer, written
    canonically, so that how it's laid out isn't part of it."""
    if pointer is None:
        return text_of(content.splitlines())
    reached = json_at(content, pointer)
    if reached is None:
        return Unreadable(f"it isn't JSON with something at #{pointer}")
    return Text((reached,))


def unit_of(text: str) -> str | None:
    """The unit suffix on a number, such as `m` in `10m`; None for a number without one, or for
    anything that isn't a number."""
    match = _UNIT.fullmatch(text.strip())
    return None if match is None or not match.group(1) else match.group(1)


def json_at(content: str, pointer: str) -> str | None:
    """The JSON at pointer in content, written canonically, or None if content isn't JSON or has
    nothing there."""
    try:
        node = json.loads(content)
    except json.JSONDecodeError:
        return None
    at = _resolve(node, pointer)
    return None if at is None else json.dumps(at.node, sort_keys=True)


@final
@dataclass(frozen=True)
class _At:
    """What a JSON Pointer reaches."""

    node: object


def _is_scalar(node: object) -> bool:
    return isinstance(node, str | int | float) and not isinstance(node, bool)


# RFC 6901's array-index: ASCII digits with no leading zero.
_ARRAY_INDEX = re.compile(r"0|[1-9][0-9]*")


def _resolve(node: object, pointer: str) -> _At | None:
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and _ARRAY_INDEX.fullmatch(token) and int(token) < len(node):
            node = node[int(token)]
        else:
            return None
    return _At(node)


@final
@dataclass(frozen=True)
class Holds:
    pass


@final
@dataclass(frozen=True)
class Fails:
    """The relation doesn't hold; shown is it written out with the values."""

    shown: str


@final
@dataclass(frozen=True)
class Incomparable:
    reason: str


type Verdict = Holds | Fails | Incomparable


def compare(op: ValueOp, left: str, right: str, formula: Formula | None) -> Verdict:
    """Whether `left <op> right [formula]` holds.

    With a formula, both are numbers. Without one, two versions (dotted numbers, at least one
    with a dot) compare on the components both give, so 24 = 24.22.1; two numbers, which may
    carry a unit suffix such as 10m or 65s, compare numerically; anything else only by = and !=.
    """
    if formula is not None:
        left_number, right_number = _number(left), _number(right)
        for text, number in ((left, left_number), (right, right_number)):
            if number is None:
                return Incomparable(f"`{text}` isn't a number, so it can't take a formula")
        assert left_number is not None and right_number is not None
        result = _apply(right_number, formula)
        if result is None:
            return Incomparable("the formula divides by zero")
        applied = format(result.normalize(), "f")
        shown = f"{left_number} {op} {right_number} {formula.text()} (= {applied})"
        return _verdict(op, _sign(left_number - result), shown)
    left_version, right_version = _version(left), _version(right)
    if left_version is not None and right_version is not None and "." in left + right:
        shared = min(len(left_version), len(right_version))
        a, b = left_version[:shared], right_version[:shared]
        return _verdict(op, (a > b) - (a < b), f"{left} {op} {right}")
    left_number, right_number = _number(left), _number(right)
    if left_number is not None and right_number is not None:
        return _verdict(op, _sign(left_number - right_number), f"{left} {op} {right}")
    match op:
        case ValueOp.EQ | ValueOp.NE:
            return _verdict(op, 0 if left == right else 1, f"`{left}` {op} `{right}`")
        case ValueOp.LT | ValueOp.LE | ValueOp.GT | ValueOp.GE:
            return Incomparable(
                f"{op} compares numbers or versions, and `{left}` {op} `{right}` aren't"
            )
        case _:
            assert_never(op)


def _verdict(op: ValueOp, sign: int, shown: str) -> Verdict:
    match op:
        case ValueOp.EQ:
            holds = sign == 0
        case ValueOp.NE:
            holds = sign != 0
        case ValueOp.LT:
            holds = sign < 0
        case ValueOp.LE:
            holds = sign <= 0
        case ValueOp.GT:
            holds = sign > 0
        case ValueOp.GE:
            holds = sign >= 0
        case _:
            assert_never(op)
    return Holds() if holds else Fails(shown)


def _apply(value: Decimal, formula: Formula) -> Decimal | None:
    match formula.arith:
        case Arith.ADD:
            return value + formula.operand
        case Arith.SUB:
            return value - formula.operand
        case Arith.MUL:
            return value * formula.operand
        case Arith.DIV:
            try:
                return value / formula.operand
            except (DivisionByZero, InvalidOperation):
                return None
        case _:
            assert_never(formula.arith)


def _sign(difference: Decimal) -> int:
    return (difference > 0) - (difference < 0)


def _number(text: str) -> Decimal | None:
    match = _NUMBER.fullmatch(text.strip())
    return None if match is None else Decimal(match.group(1).replace("_", ""))


def _version(text: str) -> tuple[int, ...] | None:
    match = _VERSION.fullmatch(text.strip())
    return None if match is None else tuple(int(part) for part in match.group(1).split("."))


# At most this many names are listed for a set's difference, and a line of text is cut to this
# length.
_MAX_NAMES = 5
_MAX_LINE = 60


def compare_members(op: SetOp, left: Members, right: Members) -> Holds | Fails:
    """Whether `left <op> right` holds, and if not, the names only one of them holds: the left
    is here, and the right there."""
    here = [name for name in left.names if name not in right.names]
    there = [name for name in right.names if name not in left.names]
    match op:
        case SetOp.SAME_SET:
            only = [(here, "here"), (there, "there")]
        case SetOp.SUBSET_OF:
            only = [(here, "here")]
        case SetOp.SUPERSET_OF:
            only = [(there, "there")]
        case SetOp.PROPER_SUBSET_OF:
            if not here and not there:
                return Fails("both hold the same names")
            only = [(here, "here")]
        case SetOp.PROPER_SUPERSET_OF:
            if not here and not there:
                return Fails("both hold the same names")
            only = [(there, "there")]
        case SetOp.DISJOINT_FROM:
            shared = [name for name in left.names if name in right.names]
            return Fails(f"{_listed(shared)} {_are(shared)} in both") if shared else Holds()
        case _:
            assert_never(op)
    shown = [f"{_listed(names)} {_are(names)} only {where}" for names, where in only if names]
    return Fails("; ".join(shown)) if shown else Holds()


def compare_member(value: Value, members: Members) -> Holds | Fails:
    """Whether members holds value, and if not, the members it isn't among."""
    if value.text in members.names:
        return Holds()
    return Fails(f"`{value.text}` isn't among {_listed(list(members.names))}")


def _are(names: list[str]) -> str:
    return "is" if len(names) == 1 else "are"


def _listed(names: list[str]) -> str:
    listed = ", ".join(f"`{name}`" for name in names[:_MAX_NAMES])
    more = len(names) - _MAX_NAMES
    return listed + (f" and {more} more" if more > 0 else "")


def compare_text(left: Text, right: Text) -> Holds | Fails:
    """Whether left and right are the same text, and if not, the first line that differs: the
    left is here, and the right there."""
    for mine, other in zip(left.lines, right.lines, strict=False):
        if mine != other:
            return Fails(f"`{_short(mine)}` here is `{_short(other)}` there")
    shared = min(len(left.lines), len(right.lines))
    if len(left.lines) > shared:
        return Fails(f"`{_short(left.lines[shared])}` is only here")
    if len(right.lines) > shared:
        return Fails(f"`{_short(right.lines[shared])}` is only there")
    return Holds()


def _short(line: str) -> str:
    return line if len(line) <= _MAX_LINE else line[: _MAX_LINE - 3] + "..."
