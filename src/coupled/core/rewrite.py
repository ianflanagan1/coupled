"""The message after a marker's label, which a repository's settings turn on, and writing it as
--fix does.

Its two parts are each turned on by a setting. tag-relations gives the site's own relations, as
seen from it, for any reader; tag-pointer tells a reader who doesn't know the convention, such
as an AI agent without the coupled-tags skill, what to search for and which file describes the
group:

    COUPLED:<key>: <label>. Must be <op> <ref>, ...
    COUPLED:<key>: <label>. Change only with every "COUPLED:<key>:" site, per <registry>.
    COUPLED:<key>: <label>. Must be <op> <ref>, ... Change only with every ... per <registry>.

It's written by --fix from the registry, so it's the same on every marker and never stale: the
lint reports a message that differs from what it would write. When the settings turn it off,
--fix drops it.
"""

import re
from typing import assert_never

from coupled.core.comments import CLOSERS
from coupled.core.markers import Marker, find_markers
from coupled.core.registry import Group, Registry, Unparseable
from coupled.core.relations import (
    Arith,
    Bare,
    Equation,
    Formula,
    Label,
    Op,
    StructuralOp,
    ValueOp,
    ref_text,
)
from coupled.core.settings import TagMessage

_OPS = "|".join(re.escape(op.value) for op in (*ValueOp, *StructuralOp))
_POINTER = r'Change only with every "COUPLED:[^"]*" site, per \S+?\.(?=\s|$)'
# A message's relations start with an op, so prose after a label, such as "Must be in MB.",
# isn't taken for one.
_RELATIONS = rf"Must be (?:{_OPS}) .*?\.(?=\s|$)"
_MESSAGE = re.compile(rf"\. (?:{_RELATIONS}(?: {_POINTER})?|{_POINTER})")

# The message wanted after each labelled marker, by its key and label. A marker not in it
# wants none.
type Wanted = dict[tuple[str, str], str]


def message(key: str, registry_file: str, relations: str | None, pointer: bool) -> str | None:
    """The message with the site's relations, if any, and the pointer if it's on, or None if
    it has neither."""
    parts: list[str] = []
    if relations is not None:
        parts.append(f"Must be {relations}.")
    if pointer:
        parts.append(f'Change only with every "COUPLED:{key}:" site, per {registry_file}.')
    return " ".join(parts) if parts else None


def wanted(
    markers: list[tuple[str, str]],
    registry: Registry | Unparseable | None,
    tag_message: TagMessage,
    registry_file: str,
) -> Wanted:
    """The message each of markers, by key and label, wants as the settings say. A marker
    whose group has no table, or that no relation names, gets its message without relations,
    so none if the pointer is off."""
    result: Wanted = {}
    for key, label in markers:
        relations = None
        if tag_message.relations:
            group = registry.groups.get(key) if isinstance(registry, Registry) else None
            relations = None if group is None else relations_of(group, label)
        found = message(key, registry_file, relations, tag_message.pointer)
        if found is not None:
            result[(key, label)] = found
    return result


def relations_of(group: Group, label: str) -> str | None:
    """The relations of the site labelled label, each as seen from it (`>= app`), or None if
    no relation names it."""
    parts: list[str] = []
    site = Label(label)
    for relation in group.relations:
        match relation:
            case Equation(left=left, op=op, right=right, formula=formula):
                if left == site:
                    parts.append(f"{op} {ref_text(right)}{_formula_text(formula)}")
                elif right == site:
                    inverse = _inverse(formula)
                    parts.append(f"{_flipped(op)} {ref_text(left)}{_formula_text(inverse)}")
            case Bare(op=op):
                parts.append(f"{op} every other site and file")
            case _:
                assert_never(relation)
    return ", ".join(parts) if parts else None


def _formula_text(formula: Formula | None) -> str:
    return "" if formula is None else " " + formula.text()


def _inverse(formula: Formula | None) -> Formula | None:
    """The formula undone: `a > b * 2` is `b < a / 2`."""
    if formula is None:
        return None
    match formula.arith:
        case Arith.ADD:
            arith = Arith.SUB
        case Arith.SUB:
            arith = Arith.ADD
        case Arith.MUL:
            arith = Arith.DIV
        case Arith.DIV:
            arith = Arith.MUL
        case _:
            assert_never(formula.arith)
    return Formula(arith, formula.operand)


def _flipped(op: Op) -> Op:
    """op from the other side: `a < b` is `b > a`."""
    match op:
        case ValueOp.EQ | ValueOp.NE | StructuralOp.SAME_AS | StructuralOp.SAME_SHAPE:
            return op
        case ValueOp.LT:
            return ValueOp.GT
        case ValueOp.LE:
            return ValueOp.GE
        case ValueOp.GT:
            return ValueOp.LT
        case ValueOp.GE:
            return ValueOp.LE
        case StructuralOp.SUBSET_OF:
            return StructuralOp.SUPERSET_OF
        case StructuralOp.SUPERSET_OF:
            return StructuralOp.SUBSET_OF
        case _:
            assert_never(op)


def written_after(after: str, wanted_message: str | None) -> str | None:
    """The text after a labelled marker as it should be, given the text after it now and the
    message it wants, if any, or None if it's right as it is."""
    found = _MESSAGE.match(after)
    rest = after if found is None else after[found.end() :]
    if wanted_message is not None:
        wanted_text = ". " + wanted_message
        if after.startswith(wanted_text) and (found is None or found.end() == len(wanted_text)):
            return None
        return wanted_text + (rest[1:] if rest.startswith(".") else rest)
    if found is None:
        return None
    if rest.startswith(" ") and rest.strip() and not rest.lstrip().startswith(CLOSERS):
        return "." + rest
    return rest


def with_messages(lines: list[str], messages: Wanted) -> list[str]:
    """lines with the message after every labelled marker written as messages wants, or
    dropped where it wants none."""
    result = list(lines)
    for placed in reversed(find_markers(lines)):
        found = placed.found
        if not isinstance(found, Marker) or found.label is None:
            continue
        line = result[placed.line]
        after = written_after(line[placed.stop :], messages.get((found.key, found.label)))
        if after is not None:
            result[placed.line] = line[: placed.stop] + after
    return result
