"""A repository's settings for its COUPLED tags, committed as .config/coupled.toml:

    version = 1                                      # the file format's version: see schema/
    exclude = ["README.md", "tests"]                 # paths not checked; none by default
    registry-file = ".config/coupled-registry.toml"  # coupled-registry.toml by default
    tag-pointer = true                               # say where each group is; off by default
    tag-relations = true                             # give each label's relations; off by default

A repository needn't have the file. The paths it excludes are skipped on every run, so the check
and --update can't disagree about them, nor about which file is the registry.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import assert_never, final

FILE = ".config/coupled.toml"

# The registry's path from the repository's root, unless the settings name another.
REGISTRY_FILE = "coupled-registry.toml"

_KNOWN = ("exclude", "registry-file", "tag-pointer", "tag-relations")


@final
@dataclass(frozen=True)
class TagMessage:
    """What follows each marker's label, each part turned on on its own: the site's own
    relations, as seen from it, then a pointer saying what to search for and which file
    describes the group."""

    # For a reader who doesn't know the convention, which a reader who does can do without.
    pointer: bool
    # For any reader, so the constraint shows where the value is edited.
    relations: bool


class Version(IntEnum):
    """The versions of coupled.toml's format the lint reads."""

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
    # The registry's path from the repository's root.
    registry_file: str
    # What follows each marker's label.
    message: TagMessage


def defaults() -> Settings:
    """The settings of a repository with no settings file."""
    return Settings([], REGISTRY_FILE, TagMessage(pointer=False, relations=False))


def settings(read: Read | Invalid | None) -> Settings | Invalid:
    """The settings a repository's file gives, read being None when it has no file."""
    match read:
        case None:
            return defaults()
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
    registry_file = table.get("registry-file", REGISTRY_FILE)
    if not isinstance(registry_file, str) or not _inside(registry_file):
        return Invalid(
            f"registry-file in {where} must be the path of a file inside the repository.", ()
        )
    pointer = table.get("tag-pointer", False)
    if not isinstance(pointer, bool):
        return Invalid(f"tag-pointer in {where} must be true or false.", ())
    relations = table.get("tag-relations", False)
    if not isinstance(relations, bool):
        return Invalid(f"tag-relations in {where} must be true or false.", ())
    return Settings(excludes, registry_file, TagMessage(pointer=pointer, relations=relations))


def _inside(path: str) -> bool:
    """Whether path, from a directory, names a file that can only be inside it: relative, with
    no empty, `.` or `..` part."""
    return all(part not in ("", ".", "..") for part in path.split("/"))
