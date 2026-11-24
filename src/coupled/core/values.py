"""Reading the value a marker describes, and comparing two values under an op and formula."""

import json
import re
from dataclasses import dataclass
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import assert_never, final

from coupled.core.comments import Syntax, is_comment_line, strip_comment
from coupled.core.markers import Placed
from coupled.core.relations import Arith, Formula, ValueOp


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


def read_value(code: str, selector: str | None) -> Reading:
    """The value in a line of code: what the selector matches (its capture group, if it has
    one), or else the one quoted literal, image tag, assignment or directive value on it."""
    if selector is not None:
        match = re.search(selector, code)
        if match is None:
            return Unreadable(f"the selector @/{selector}/ doesn't match `{code}`")
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


def read_file_value(content: str, pointer: str | None) -> Reading | None:
    """The value in a file a group refers to: at the JSON Pointer, or if there's none, the whole
    file when it's one line. None when there's no pointer and the file is longer, so the ref
    only lists the file."""
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
    node = at.node
    if isinstance(node, bool) or not isinstance(node, str | int | float):
        return Unreadable(f"#{pointer} isn't a string or number")
    return Value(str(node))


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


def _resolve(node: object, pointer: str) -> _At | None:
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
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
