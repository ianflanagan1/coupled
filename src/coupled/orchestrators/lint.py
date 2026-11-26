"""Linting a repository's COUPLED groups: read its settings; gather the markers in its files, its
registry and the files in it that the registry's groups refer to; with --fix, write or drop the
message after each marker's label, as the settings say, and gather again; with --update, record
the groups it names in the registry's reviewed section; then check them. Files in other repositories
aren't read."""

from dataclasses import dataclass
from typing import Protocol, final

from coupled.core import registry as registries
from coupled.core import review
from coupled.core.check import (
    Content,
    FileRead,
    Missing,
    Problem,
    Site,
    check,
    file_paths,
    file_sites,
    markers,
    no_file_sites,
    unchecked,
)
from coupled.core.markers import Marker
from coupled.core.registry import Registry, Unparseable
from coupled.core.rewrite import wanted, with_messages
from coupled.core.settings import FILE, ROOT_FILE, Invalid, Read, Settings, one_file, settings


class MarkerSearch(Protocol):
    def paths(self, root: str) -> list[str]:
        """The path, relative to root, of every file under root holding `COUPLED:`."""
        ...


class Files(Protocol):
    def read(self, path: str) -> str | None:
        """The content of the file at path, or None if it can't be read."""
        ...

    def write(self, path: str, content: str) -> None: ...


class SettingsFile(Protocol):
    def read(self, root: str, name: str) -> Read | Invalid | None:
        """The settings file at name from the repository's root, None if there's none, or
        Invalid if it isn't a settings file in a version the lint reads."""
        ...


@final
@dataclass(frozen=True)
class Report:
    problems: list[Problem]
    # Each key, in the order first found, with its sites' locations.
    keys: list[tuple[str, list[str]]]
    # The repositories groups refer to files in, which weren't checked.
    unchecked: list[str]
    # The sites in no file, as `<key> <label>`, which weren't checked.
    no_file_sites: list[str]
    # The files --fix rewrote markers in.
    fixed: list[str]
    # Whether --update changed the registry.
    updated: bool
    # The registry's path from the root, as the repository's settings give it.
    registry_file: str


@final
@dataclass(frozen=True)
class _Gathered:
    sites: list[Site]
    registry: Registry | Unparseable | None
    # The registry's text, or None if there's none.
    registry_text: str | None
    files: dict[str, FileRead]
    # A problem for each file holding markers that couldn't be read.
    unreadable: list[Problem]


@final
class Lint:
    def __init__(self, search: MarkerSearch, files: Files, settings: SettingsFile) -> None:
        self._search = search
        self._files = files
        self._settings = settings

    def run(self, root: str, excludes: list[str], update: list[str], fix: bool) -> Report | Invalid:
        """Lints the repository at root, leaving out the paths its settings exclude and the
        excludes given, after recording the groups of the keys in update as reviewed. Invalid,
        with nothing changed, when its settings can't be used."""
        found = settings(
            one_file(self._settings.read(root, FILE), self._settings.read(root, ROOT_FILE))
        )
        if isinstance(found, Invalid):
            return found
        excludes = found.excludes + excludes
        gathered = self._gather(root, excludes, found)
        fixed: list[str] = []
        if fix:
            fixed = self._fix(root, gathered, found)
            if fixed:
                gathered = self._gather(root, excludes, found)
        sites = gathered.sites
        registry = gathered.registry

        updated = False
        problems = gathered.unreadable + check(
            sites, registry, gathered.files, found.registry_file, found.message
        )
        if isinstance(registry, Registry):
            now = review.current(sites, registry, gathered.files)
            old = registry.reviewed
            unknown = [key for key in update if key not in registry.groups]
            problems += [
                Problem(found.registry_file, f"--update {key}: there's no group COUPLED:{key}:")
                for key in unknown
            ]
            if update and not unknown and gathered.registry_text is not None:
                new = review.reviewed(old, now, update)
                text = registries.with_reviewed(gathered.registry_text, new)
                if text != gathered.registry_text:
                    self._files.write(root + "/" + found.registry_file, text)
                    updated = True
                old = new
            problems += review.compare(old, now, found.registry_file)
        keys: dict[str, list[str]] = {}
        for site in sites:
            if isinstance(site.found, Marker):
                keys.setdefault(site.found.key, []).append(site.where)
        return Report(
            problems,
            list(keys.items()),
            unchecked(registry),
            no_file_sites(registry),
            fixed,
            updated,
            found.registry_file,
        )

    def _gather(self, root: str, excludes: list[str], found: Settings) -> _Gathered:
        paths = [
            path
            for path in self._search.paths(root)
            if not review.excluded(path, excludes) and path != found.registry_file
        ]
        sites: list[Site] = []
        unreadable: list[Problem] = []
        for path in paths:
            text = self._files.read(root + "/" + path)
            if text is None:
                unreadable.append(
                    Problem(path, "Can't read this file as UTF-8 to check its markers")
                )
                continue
            sites += file_sites(path, text.splitlines())
        registry_text = self._files.read(root + "/" + found.registry_file)
        registry = None if registry_text is None else registries.parse(registry_text)
        files: dict[str, FileRead] = {}
        if isinstance(registry, Registry):
            files = {path: self._read(root, path) for path in file_paths(registry)}
        return _Gathered(sites, registry, registry_text, files, unreadable)

    def _fix(self, root: str, gathered: _Gathered, found: Settings) -> list[str]:
        """Writes or drops the message after each marker's label, returning the paths of the
        files changed."""
        paths: list[str] = []
        for site in gathered.sites:
            path = site.where.rsplit(":", 1)[0]
            if isinstance(site.found, Marker) and path not in paths:
                paths.append(path)
        messages = wanted(
            markers(gathered.sites), gathered.registry, found.message, found.registry_file
        )
        changed: list[str] = []
        for path in paths:
            text = self._files.read(root + "/" + path)
            if text is None:
                continue
            lines = with_messages(text.splitlines(), messages)
            new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
            if new_text != text:
                self._files.write(root + "/" + path, new_text)
                changed.append(path)
        return changed

    def _read(self, root: str, path: str) -> FileRead:
        content = self._files.read(root + "/" + path)
        return Missing() if content is None else Content(content)
