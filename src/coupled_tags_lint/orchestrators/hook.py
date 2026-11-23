"""The Claude Code hooks: the gate, which stops the first edit in a session to a line a COUPLED
marker covers until Claude has been shown its group, and the context hook, which shows Claude
the groups in a file it reads. A group shown by either isn't shown again in the session. Files
the repository's settings exclude, and its registry, are left alone."""

import os
from typing import Protocol, final

from coupled_tags_lint.core import hook
from coupled_tags_lint.core.registry import entry_text
from coupled_tags_lint.core.review import excluded
from coupled_tags_lint.core.settings import Invalid, Read, Settings, defaults, settings


class Repositories(Protocol):
    def root(self, directory: str) -> str | None:
        """The top of the git work tree holding directory, or None outside one."""
        ...

    def hits(self, root: str, text: str) -> list[str]:
        """Each line holding text in the work tree at root, as `path:line:text`, path relative
        to root."""
        ...


class Files(Protocol):
    def read(self, path: str) -> str | None:
        """The content of the file at path, or None if it can't be read."""
        ...


class SettingsFile(Protocol):
    def read(self, root: str) -> Read | Invalid | None:
        """The settings file of the repository at root, None if it has none, or Invalid if it
        isn't a settings file in a version the lint reads."""
        ...


class Shown(Protocol):
    def unseen(self, session: str, keys: list[str]) -> list[str]:
        """The keys the session hasn't been shown yet, which are marked shown."""
        ...


@final
class Hook:
    def __init__(
        self, repositories: Repositories, files: Files, settings: SettingsFile, shown: Shown
    ) -> None:
        self._repositories = repositories
        self._files = files
        self._settings = settings
        self._shown = shown

    def gate(self, session: str, path: str, changes: list[hook.Change]) -> str | None:
        """Why an edit to the file at path should stop, or None if it can go ahead."""
        content = self._files.read(path)
        if content is None:
            return None
        found = self._found(path)
        if found is None:
            return None
        root, chosen = found
        keys = self._shown.unseen(session, hook.touched_keys(content, changes))
        if not keys:
            return None
        return hook.gate_reason(self._groups(root, chosen, keys), chosen.registry)

    def context(self, session: str, path: str) -> str | None:
        """What to tell Claude about the groups in the file at path it has read, or None."""
        content = self._files.read(path)
        if content is None or "COUPLED:" not in content:
            return None
        found = self._found(path)
        if found is None:
            return None
        root, chosen = found
        keys = self._shown.unseen(session, hook.keys_in(content))
        if not keys:
            return None
        shown = path if root is None else os.path.relpath(path, root)
        return hook.context(shown, self._groups(root, chosen, keys), chosen.registry)

    def _found(self, path: str) -> tuple[str | None, Settings] | None:
        """The root of the repository holding path, or None outside one, and its settings; or
        None if its settings leave path alone."""
        root = self._repositories.root(os.path.dirname(path))
        if root is None:
            return None, defaults()
        chosen = settings(self._settings.read(root))
        if isinstance(chosen, Invalid):
            chosen = defaults()
        relative = os.path.relpath(path, root)
        if relative == chosen.registry or excluded(relative, chosen.excludes):
            return None
        return root, chosen

    def _groups(self, root: str | None, chosen: Settings, keys: list[str]) -> list[hook.Group]:
        if root is None:
            return [hook.Group(key, None, None) for key in keys]
        text = self._files.read(os.path.join(root, chosen.registry))
        groups: list[hook.Group] = []
        for key in keys:
            sites = [
                hit
                for hit in self._repositories.hits(root, f"COUPLED:{key}:")
                if not excluded(hit.split(":", 1)[0], chosen.excludes)
                and hit.split(":", 1)[0] != chosen.registry
            ]
            table = None if text is None else entry_text(text, key)
            groups.append(hook.Group(key, sites, table))
        return groups
