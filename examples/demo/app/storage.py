"""The object store's notice that an upload has landed in it."""

from dataclasses import dataclass


# COUPLED:storage-event: handler
@dataclass(frozen=True)
class ObjectCreated:
    bucket: str
    key: str
    size: int
    etag: str


# COUPLED:storage-event:END
