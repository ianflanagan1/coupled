"""The message after a marker's label, which a repository's settings turn on, and writing it as
--fix does.

The message tells a reader who doesn't know the convention, such as an AI agent without the
coupled-tags skill, what to search for and where the group is described:

    COUPLED:<key>: <label>. Change only with every "COUPLED:<key>:" site, per <registry>.

It's written by --fix from the key and the registry's path, so it's the same on every marker.
When the settings turn it off, --fix drops it.
"""

import re

from coupled_tags_lint.core.markers import Marker, find_markers

_MESSAGE = re.compile(r'\. Change only with every "COUPLED:[^"]*" site, per \S+?\.(?=\s|$)')
_CLOSERS = ("-->", "*/", "#}")


def message(key: str, registry_file: str) -> str:
    return f'Change only with every "COUPLED:{key}:" site, per {registry_file}.'


def written_after(after: str, key: str, registry_file: str, on: bool) -> str | None:
    """The text after a labelled marker of key as it should be, given the text after it now
    and whether messages are on, or None if it's right as it is."""
    found = _MESSAGE.match(after)
    rest = after if found is None else after[found.end() :]
    if on:
        wanted = ". " + message(key, registry_file)
        if after.startswith(wanted):
            return None
        return wanted + (rest[1:] if rest.startswith(".") else rest)
    if found is None:
        return None
    if rest.startswith(" ") and rest.strip() and not rest.lstrip().startswith(_CLOSERS):
        return "." + rest
    return rest


def with_messages(lines: list[str], registry_file: str, on: bool) -> list[str]:
    """lines with the message after every labelled marker written, or dropped, as on says."""
    result = list(lines)
    for placed in reversed(find_markers(lines)):
        found = placed.found
        if not isinstance(found, Marker) or found.label is None:
            continue
        line = result[placed.line]
        after = written_after(line[placed.stop :], found.key, registry_file, on)
        if after is not None:
            result[placed.line] = line[: placed.stop] + after
    return result
