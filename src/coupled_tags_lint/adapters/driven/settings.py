"""Reading a repository's settings file from the local disk with repo-settings, which finds
.config/ianf-coupled-tags.toml and checks its version."""

from pathlib import Path
from typing import assert_never, final

from coupled_tags_lint.core.settings import PURPOSE, Invalid, Read, Version


@final
class LocalSettings:
    def read(self, root: str) -> Read | Invalid | None:
        """The file under root, which is what the lock's path and excluded paths are relative
        to, whether or not root is a worktree's own root."""
        # Imported here, not above, so the hook's common case, a file read that holds no
        # markers, doesn't pay for loading repo-settings and tomlkit.
        import repo_settings

        found = repo_settings.read_file(Path(root) / repo_settings.location(PURPOSE), Version)
        match found:
            case repo_settings.Settings():
                return Read(found.version, found.table, found.where)
            case repo_settings.Missing():
                return None
            case repo_settings.Invalid():
                return Invalid(found.message, found.details)
            case _:
                assert_never(found)
