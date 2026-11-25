"""What the service records about an upload."""

from dataclasses import dataclass
from typing import Literal


# COUPLED:upload-shape: model
# COUPLED:upload-columns: model /^(\w+): /
@dataclass(frozen=True)
class Upload:
    id: str
    name: str
    size_bytes: int
    # COUPLED:upload-status: app
    status: Literal["pending", "scanning", "stored", "rejected"]


# COUPLED:upload-columns:END
# COUPLED:upload-shape:END


# The status of an upload the service has only just received.
NEW_STATUS = "pending"  # COUPLED:upload-status: new
