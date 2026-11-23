"""A repository's settings for its COUPLED tags, committed as .config/ianf-coupled-tags.toml:

    version = 1                     # the version of the file's format: see schema/
    exclude = ["README.md", "tests"]  # path prefixes whose tags aren't checked; none by default
    lock-file = ".config/coupled-tags.lock"  # the lock file; .coupled-tags.lock by default

A repository needn't have the file. The paths it excludes are skipped on every run, so the check
and --update can't disagree about them, nor about which file is the lock.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import assert_never, final

from coupled_tags_lint.core.lock import LOCK_FILE

PURPOSE = "coupled-tags"

_KNOWN = ("exclude", "lock-file")


class Version(IntEnum):
    """The versions of ianf-coupled-tags.toml's format the lint reads."""

    V1 = 1


@final
@dataclass(frozen=True)
class Read:
    """A settings file as it was read: the version of its format, and its other settings."""

    version: Version
    table: dict[str, object]
    # Which file it is, for messages.
    where: str


@final
@dataclass(frozen=True)
class Invalid:
    """Why a settings file can't be used: a message, then any lines of detail."""

    message: str
    details: tuple[str, ...]


@final
@dataclass(frozen=True)
class Settings:
    # The path prefixes whose tags aren't checked, without a trailing slash.
    excludes: list[str]
    # The lock file's path from the repository's root.
    lock: str


def settings(read: Read | Invalid | None) -> Settings | Invalid:
    """The settings a repository's file gives, read being None when it has no file."""
    match read:
        case None:
            return Settings([], LOCK_FILE)
        case Invalid():
            return read
        case Read():
            match read.version:
                case Version.V1:
                    return _v1(read.table, read.where)
                case _:
                    assert_never(read.version)
        case _:
            assert_never(read)


def _v1(table: dict[str, object], where: str) -> Settings | Invalid:
    if unknown := sorted(table.keys() - set(_KNOWN)):
        return Invalid(f"Unknown settings in {where}: {', '.join(unknown)}.", ())
    exclude = table.get("exclude", [])
    if not isinstance(exclude, list):
        return Invalid(f"exclude in {where} must be a list of paths.", ())
    excludes: list[str] = []
    for path in exclude:
        if not isinstance(path, str) or not path:
            return Invalid(f"exclude in {where} must be a list of paths.", ())
        excludes.append(path.rstrip("/"))
    lock = table.get("lock-file", LOCK_FILE)
    if not isinstance(lock, str) or not _inside(lock):
        return Invalid(
            f"lock-file in {where} must be the path of a file inside the repository.", ()
        )
    return Settings(excludes, lock)


def _inside(path: str) -> bool:
    """Whether path, from a directory, names a file that can only be inside it: relative, with
    no empty, `.` or `..` part."""
    return all(part not in ("", ".", "..") for part in path.split("/"))
