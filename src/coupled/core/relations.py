"""The relations a group's table in the registry states between its sites.

A relation is `<label> <op> <label> [<arith> <number>]`, an equation: the first site's value, by
op, the second's through the formula. A site is named by its label, whether a marker carries it
or the group's table gives it to a site with no marker (see registry.py).

An op is of one of four kinds, by what it reads each site as, and a group uses one kind. Value
ops compare single values, set ops the names each site holds, and the text op the sites' text,
so the lint checks all three. Judged ops relate code or prose that only a reader can compare.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import assert_never, final

from coupled.core.markers import NAME_PATTERN


class ValueOp(StrEnum):
    """An op that compares the single values at two sites."""

    EQ = "="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="


class SetOp(StrEnum):
    """An op that compares the names two sites hold, such as an enum's members."""

    SAME_SET = "same-set"
    SUBSET_OF = "subset-of"
    SUPERSET_OF = "superset-of"


class TextOp(StrEnum):
    """An op that compares the text of two sites, such as a block copied between two files."""

    SAME_TEXT = "same-text"


class JudgedOp(StrEnum):
    """An op relating code or prose that only a reader can compare: the lint records each site
    and reports a change to one, but can't tell whether the relation holds."""

    SAME_AS = "same-as"
    SAME_SHAPE = "same-shape"
    DESCRIPTION_OF = "description-of"
    DESCRIBED_BY = "described-by"


type Op = ValueOp | SetOp | TextOp | JudgedOp


class Kind(StrEnum):
    """What an op reads each site as: one value, a set of names, text, or something only a
    reader can compare."""

    VALUE = "value"
    SET = "set"
    TEXT = "text"
    JUDGED = "judged"


def kind_of(op: Op) -> Kind:
    match op:
        case ValueOp():
            return Kind.VALUE
        case SetOp():
            return Kind.SET
        case TextOp():
            return Kind.TEXT
        case JudgedOp():
            return Kind.JUDGED
        case _:
            assert_never(op)


OPS: tuple[Op, ...] = (*ValueOp, *SetOp, *TextOp, *JudgedOp)

OPS_TEXT = " ".join(OPS)


class Arith(StrEnum):
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"


@final
@dataclass(frozen=True)
class Formula:
    """What the second ref's value goes through before it's compared: `<arith> <operand>`."""

    arith: Arith
    operand: Decimal

    def text(self) -> str:
        return f"{self.arith} {self.operand}"


@final
@dataclass(frozen=True)
class Relation:
    """`<left> <op> <right> [<arith> <number>]`, left and right being sites' labels."""

    left: str
    op: Op
    right: str
    formula: Formula | None

    def text(self) -> str:
        formula = "" if self.formula is None else " " + self.formula.text()
        return f"{self.left} {self.op} {self.right}{formula}"


LABEL = re.compile(NAME_PATTERN)
_NUMBER = re.compile(r"\d[\d_]*(?:\.\d+)?")


def parse_relation(text: str) -> Relation | str:
    """The relation text states, or a message saying how to write it."""
    words = text.split()
    if len(words) not in (3, 5):
        return f"Write `{text}` as `<label> <op> <label> [<arith> <number>]`, separated by spaces"
    op = _op(words[1])
    if op is None:
        return f"Use one of {OPS_TEXT} between the labels of `{text}`"
    for label in (words[0], words[2]):
        if LABEL.fullmatch(label) is None:
            return (
                f"Name each site in `{text}` by its label, in lowercase letters and digits "
                f"joined by single hyphens: `{label}` isn't one. A file that can't hold a "
                "marker gets a label in `has-no-marker`"
            )
    formula = None
    if len(words) == 5:
        if words[3] not in [*Arith] or _NUMBER.fullmatch(words[4]) is None:
            return f"Write the formula of `{text}` as `<arith> <number>`, its arith one of + - * /"
        formula = Formula(Arith(words[3]), Decimal(words[4].replace("_", "")))
    return Relation(words[0], op, words[2], formula)


def _op(text: str) -> Op | None:
    return next((op for op in OPS if op == text), None)
