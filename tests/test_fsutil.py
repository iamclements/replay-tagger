from __future__ import annotations

import os
import stat
from pathlib import Path

from replaytagger.fsutil import write_private


def test_write_private_creates_owner_only_file(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "secret"
    write_private(target, "s3cret")
    assert target.read_text() == "s3cret"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_write_private_tightens_existing_file(tmp_path: Path) -> None:
    target = tmp_path / "secret"
    target.write_text("old")
    os.chmod(target, 0o644)
    write_private(target, "new")
    assert target.read_text() == "new"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
