"""Finding COUPLED markers in a file's lines.

A marker is `COUPLED:<key>: <label>`, in a comment, or as plain text where the file has no
comments, such as Markdown. Its key names a group, which the registry describes; its label
names this site within the group, for the registry's relations. Prose goes before `COUPLED:`,
or after the label and a `.`: `COUPLED:<key>: <label>. <prose>`.

`COUPLED:<key>:END` closes the block the nearest marker of its key above it opens, so that the
marker describes every line between them.

A file holding `COUPLED:IGNORE-FILE` alone on a line, or alone in a comment on it, has no
markers: its `COUPLED:` text is all examples, such as the coupled-tags skill's, wherever it's
copied. Written anywhere else in a line, it's a mention, which doesn't.
"""

import re
from dataclasses import dataclass, replace
from typing import assert_never, final

from coupled.core.comments import CLOSERS

# A key or label: lowercase letters and digits, in words joined by single hyphens. A key
# starting with a hyphen would read as an option to a search run on the key alone.
NAME_PATTERN = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_NAME = re.compile(NAME_PATTERN)
_END = re.compile(rf"({NAME_PATTERN}):END(?![A-Za-z0-9_-])")
_KEY = re.compile(rf"({NAME_PATTERN}):")
# A key written as text to search for, quoted: `"COUPLED:upload-limit:"`, not a marker.
_SEARCH = re.compile(rf"{NAME_PATTERN}:['\"`]")
_OLD_TAG = re.compile(rf"{NAME_PATTERN}:\[")
_IGNORE_FILE = "IGNORE-FILE"
# The directive alone on its line, but for whitespace and comment syntax around it.
_IGNORES_FILE = re.compile(rf"[^\w]*COUPLED:{_IGNORE_FILE}[^\w]*")


@final
@dataclass(frozen=True)
class Marker:
    """`COUPLED:<key>: <label>`, label None when it has none, with what's wrong with it on its
    own, as messages saying how to fix it."""

    key: str
    label: str | None
    problems: tuple[str, ...]

    def text(self) -> str:
        """The marker as it's written, with its label."""
        return marker_text(self.key, self.label)


def marker_text(key: str, label: str | None) -> str:
    return f"COUPLED:{key}:" + ("" if label is None else f" {label}")


@final
@dataclass(frozen=True)
class End:
    """`COUPLED:<key>:END`, with what's wrong with how it closes a block, as messages saying how
    to fix it."""

    key: str
    problems: tuple[str, ...]


@final
@dataclass(frozen=True)
class Malformed:
    """Text that starts like a marker but isn't one, with a message saying how to write it."""

    problem: str


type Found = Marker | End | Malformed


@final
@dataclass(frozen=True)
class Placed:
    """A marker or END found in a file's lines: what it is, the index of its line, the column
    `COUPLED:` starts at and the column after its label, or after its key's `:` when it has no
    label, and the index of the line holding the END that closes its block, or None if nothing
    closes it."""

    found: Found
    line: int
    start: int
    stop: int
    close: int | None


def key_of(found: Found) -> str | None:
    match found:
        case Marker(key=key) | End(key=key):
            return key
        case Malformed():
            return None
        case _:
            assert_never(found)


def find_markers(lines: list[str]) -> list[Placed]:
    """The markers and ENDs in a file's lines, in order, each marker with the END closing its
    block. Mentions in prose such as `COUPLED:<key>:`, and quoted search text such as
    `"COUPLED:upload-limit:"`, aren't markers. A file holding the ignore directive has none."""
    if ignores_file(lines):
        return []
    placed: list[Placed] = []
    for index, line in enumerate(lines):
        column = 0
        while (start := line.find("COUPLED:", column)) >= 0:
            column = start + len("COUPLED:")
            rest = line[column:]
            if not re.match(r"[A-Za-z0-9_-]", rest) or _SEARCH.match(rest):
                continue
            if rest.startswith(_IGNORE_FILE) and not re.match(r"[\w-]", rest[len(_IGNORE_FILE) :]):
                continue
            end = _END.match(rest)
            if end is not None:
                placed.append(Placed(End(end.group(1), ()), index, start, column + end.end(), None))
                column += end.end()
                continue
            found, length = _marker(rest)
            placed.append(Placed(found, index, start, column + length, None))
            column += length
    return _paired(placed)


def ignores_file(lines: list[str]) -> bool:
    """Whether a file's lines hold the ignore directive on a line of its own, so that its
    `COUPLED:` text is examples, not markers."""
    return any(_IGNORES_FILE.fullmatch(line) for line in lines)


def _marker(rest: str) -> tuple[Found, int]:
    """What the text after `COUPLED:` holds, and how much of it that is."""
    if _OLD_TAG.match(rest):
        return Malformed(
            "Write a marker, `COUPLED:<key>: <label>`, and move the relation in brackets to the "
            "group's table in the registry"
        ), 0
    key = _KEY.match(rest)
    if key is None:
        return Malformed(
            "Malformed marker. Must be `COUPLED:<key>: <label>`, or `COUPLED:<key>:END` "
            "closing a block, with a key and label of lowercase letters and digits, in words "
            "joined by single hyphens"
        ), 0
    after = rest[key.end() :]
    unlabelled = Marker(
        key.group(1),
        None,
        (
            f"Label this site: `COUPLED:{key.group(1)}: <label>`, the name the registry's "
            "relations give it",
        ),
    )
    if not after.strip() or after.lstrip().startswith(CLOSERS):
        return unlabelled, key.end()
    if not after.startswith(" "):
        return Malformed(
            f"Put a space between `COUPLED:{key.group(1)}:` and the site's label"
        ), key.end()
    label = _NAME.match(after, 1)
    if label is None:
        return unlabelled, key.end()
    following = after[label.end() :]
    if following and not following.startswith(".") and not following.lstrip().startswith(CLOSERS):
        if following.startswith(" ") and following.strip():
            return Marker(
                key.group(1),
                label.group(),
                (
                    f"End the label with `.` before the prose after it: "
                    f"`COUPLED:{key.group(1)}: {label.group()}. <prose>`",
                ),
            ), key.end() + label.end()
        return Malformed(
            "Write the label in lowercase letters and digits, in words joined by single hyphens"
        ), key.end()
    return Marker(key.group(1), label.group(), ()), key.end() + label.end()


def _paired(placed: list[Placed]) -> list[Placed]:
    """placed, with each END closing the nearest marker of its key above it that no END closes
    yet, and each END's problems: one closing nothing, and blocks that nest in one of their own
    key or overlap another."""
    closes: dict[int, int] = {}
    problems: dict[int, list[str]] = {}
    for position, item in enumerate(placed):
        if not isinstance(item.found, End):
            continue
        key = item.found.key
        mine = problems.setdefault(position, [])
        opens = [
            earlier
            for earlier in range(position)
            if isinstance(placed[earlier].found, Marker) and key_of(placed[earlier].found) == key
        ]
        free = [earlier for earlier in opens if earlier not in closes]
        if not free:
            mine.append(
                f"Open this block with a marker of COUPLED:{key}: above it, or drop this END"
            )
            continue
        opening = free[-1]
        closes[opening] = position
        inner = [earlier for earlier in opens if opening < earlier and earlier in closes]
        if inner:
            mine.append(
                f"This block holds another of COUPLED:{key}: (line {placed[inner[0]].line + 1}): "
                "blocks of one key can't nest"
            )
    for opening, closing in closes.items():
        for other, other_closing in closes.items():
            if opening < other < closing < other_closing:
                problems[closing].append(
                    f"Blocks can nest but not overlap: the block of COUPLED:"
                    f"{key_of(placed[other].found)}: on line {placed[other].line + 1} runs on "
                    "past this END"
                )
    result: list[Placed] = []
    for position, item in enumerate(placed):
        if isinstance(item.found, End):
            item = replace(item, found=End(item.found.key, tuple(problems[position])))
        elif position in closes:
            item = replace(item, close=placed[closes[position]].line)
        result.append(item)
    return result
