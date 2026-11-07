from __future__ import annotations

import os
from pathlib import Path


def write_private(path: Path, text: str) -> None:
    """Write text to path with owner-only (0600) permissions.

    The file is created with mode 0600 so the secret is never briefly world-readable,
    and the mode is re-applied afterwards to tighten files that already existed with
    looser permissions.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)
