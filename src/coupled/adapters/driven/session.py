"""Which COUPLED groups a Claude Code session has been shown, as a marker file per key in
$TMPDIR/claude-coupled/<session>/."""

import os
import re
import tempfile
from typing import final


@final
class SessionMarks:
    def unseen(self, session: str, keys: list[str]) -> list[str]:
        """The keys the session hasn't been shown yet, which are marked shown."""
        state = os.path.join(
            tempfile.gettempdir(),
            "claude-coupled",
            re.sub(r"[^A-Za-z0-9_-]", "_", session) or "unknown",
        )
        os.makedirs(state, exist_ok=True)
        unseen: list[str] = []
        for key in keys:
            try:
                with open(os.path.join(state, key), "x"):
                    unseen.append(key)
            except FileExistsError:
                pass
        return unseen
