"""Reading and writing files on the local disk."""

import os
from typing import final


@final
class LocalFiles:
    def read(self, path: str) -> str | None:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            return None

    def write(self, path: str, content: str) -> None:
        """Writes the file at path, making the directories above it that aren't there."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
