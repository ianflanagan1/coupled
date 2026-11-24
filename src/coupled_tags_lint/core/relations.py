"""The relations a group's table in the registry states between its sites and files.

A relation is `<ref> <op> <ref> [<arith> <number>]`, an equation: the first ref's value, by op,
the second's through the formula. Or it's a bare op, `=`, `same-as` or `same-shape`, alone:
every site and file of the group is the same. A ref is a site, by its marker's label
(`proxy`), or a file that can't hold a marker: `./<path>[?][#<pointer>]` in this repository, or
`//<git-host>/<owner>/<name>/<path>[?][#<pointer>]` in another.
"""

import re
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum
from typing import assert_never, final

from coupled_tags_lint.core.markers import NAME_PATTERN


class ValueOp(StrEnum):
    """An op that compares the values at two sites."""

    EQ = "="
    NE = "!="
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="


class StructuralOp(StrEnum):
    """An op relating code or structure, which an agent judges and the lint doesn't compare."""

    SAME_AS = "same-as"
    SAME_SHAPE = "same-shape"
    SUBSET_OF = "subset-of"
    SUPERSET_OF = "superset-of"


type Op = ValueOp | StructuralOp

# The ops a relation can be alone, when every site and file of the group is the same.
BARE_OPS: frozenset[Op] = frozenset({ValueOp.EQ, StructuralOp.SAME_AS, StructuralOp.SAME_SHAPE})

OPS_TEXT = " ".join([*ValueOp, *StructuralOp])


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
class Label:
    """A site, by its marker's label."""

    text: str


@final
@dataclass(frozen=True)
class FileRef:
    """A file that can't hold a marker: in this repository (repo None), or in the repository
    repo, `<git-host>/<owner>/<name>`, which the lint doesn't read. An optional file (`?`) is
    only sometimes there, such as an untracked .env, so its absence isn't a problem. pointer is
    a JSON Pointer to the value in it."""

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


type Ref = Label | FileRef


def ref_text(ref: Ref) -> str:
    match ref:
        case Label(text):
            return text
        case FileRef():
            return ref.text()
        case _:
            assert_never(ref)


@final
@dataclass(frozen=True)
class Equation:
    """`<left> <op> <right> [<arith> <number>]`."""

    left: Ref
    op: Op
    right: Ref
    formula: Formula | None

    def text(self) -> str:
        formula = "" if self.formula is None else " " + self.formula.text()
        return f"{ref_text(self.left)} {self.op} {ref_text(self.right)}{formula}"


@final
@dataclass(frozen=True)
class Bare:
    """An op alone: every site and file of the group is the same."""

    op: Op

    def text(self) -> str:
        return str(self.op)


type Relation = Equation | Bare

_LABEL = re.compile(NAME_PATTERN)
_NUMBER = re.compile(r"\d[\d_]*(?:\.\d+)?")
_LOCAL_FILE = re.compile(r"\./([^\s?#/][^\s?#]*)(\?)?(?:#(/\S*))?")
_REMOTE_FILE = re.compile(r"//([^\s/?#]+/[^\s/?#]+/[^\s/?#]+)/([^\s?#]+)(\?)?(?:#(/\S*))?")

FILE_FORM = (
    "Write a file as ./<path>[?][#<pointer>] in this repository, or "
    "//<git-host>/<owner>/<name>/<path>[?][#<pointer>] in another, its pointer a JSON Pointer "
    "starting /"
)


def parse_relation(text: str) -> Relation | str:
    """The relation text states, or a message saying how to write it."""
    words = text.split()
    if len(words) == 1:
        op = _op(words[0])
        if op is None or op not in BARE_OPS:
            return (
                f"Write `{text}` as `<ref> <op> <ref>`; only = same-as same-shape can stand "
                "alone, for a group whose sites and files are all the same"
            )
        return Bare(op)
    if len(words) not in (3, 5):
        return f"Write `{text}` as `<ref> <op> <ref> [<arith> <number>]`, separated by spaces"
    op = _op(words[1])
    if op is None:
        return f"Use one of {OPS_TEXT} between the refs of `{text}`"
    left, right = parse_ref(words[0]), parse_ref(words[2])
    for ref in (left, right):
        if isinstance(ref, str):
            return ref
    assert not isinstance(left, str) and not isinstance(right, str)
    formula = None
    if len(words) == 5:
        if words[3] not in [*Arith] or _NUMBER.fullmatch(words[4]) is None:
            return f"Write the formula of `{text}` as `<arith> <number>`, its arith one of + - * /"
        formula = Formula(Arith(words[3]), Decimal(words[4].replace("_", "")))
    return Equation(left, op, right, formula)


def parse_ref(text: str) -> Ref | str:
    """The site or file text names, or a message saying how to write it."""
    if text.startswith(("./", "//")):
        ref = parse_file(text)
        return f"{FILE_FORM}, not `{text}`" if ref is None else ref
    if _LABEL.fullmatch(text) is None:
        return (
            f"Name a site by its marker's label, in lowercase letters and digits joined by "
            f"single hyphens, or a file by ./<path>: `{text}` is neither"
        )
    return Label(text)


def parse_file(text: str) -> FileRef | None:
    """The file text refers to, or None if it isn't written as one."""
    local = _LOCAL_FILE.fullmatch(text)
    if local is not None:
        return FileRef(None, local.group(1), local.group(2) is not None, local.group(3))
    remote = _REMOTE_FILE.fullmatch(text)
    if remote is not None:
        return FileRef(
            remote.group(1), remote.group(2), remote.group(3) is not None, remote.group(4)
        )
    return None


def _op(text: str) -> Op | None:
    for family in (ValueOp, StructuralOp):
        for op in family:
            if op == text:
                return op
    return None


def refs(relation: Relation) -> list[Ref]:
    match relation:
        case Equation(left=left, right=right):
            return [left, right]
        case Bare():
            return []
        case _:
            assert_never(relation)
