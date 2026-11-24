"""Stored file names."""

import re


# COUPLED:safe-name: app
def safe_name(name: str) -> str:
    return re.sub(r"[^a-z0-9.-]+", "-", name.lower()).strip("-")


# COUPLED:safe-name:END
