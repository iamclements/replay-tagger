from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class StateDB:
    """Tracks processed files and YouTube upload IDs to avoid redundant work."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    file_path      TEXT PRIMARY KEY,
                    game_name      TEXT NOT NULL,
                    file_size      INTEGER NOT NULL,
                    mtime          REAL NOT NULL,
                    tagged_at      TEXT NOT NULL,
                    youtube_id     TEXT
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _fingerprint(self, file_path: Path) -> tuple[int, float]:
        stat = file_path.stat()
        return stat.st_size, stat.st_mtime

    def is_tagged(self, file_path: Path) -> bool:
        """Returns True if the file was tagged and hasn't changed since."""
        if not file_path.exists():
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT file_size, mtime FROM processed_files WHERE file_path = ?",
                (str(file_path),),
            ).fetchone()
        if row is None:
            return False
        current_size, current_mtime = self._fingerprint(file_path)
        return bool(row["file_size"] == current_size and abs(row["mtime"] - current_mtime) < 1.0)

    def mark_tagged(self, file_path: Path, game_name: str) -> None:
        size, mtime = self._fingerprint(file_path)
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_files
                    (file_path, game_name, file_size, mtime, tagged_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(file_path), game_name, size, mtime, now),
            )

    def mark_uploaded(self, file_path: Path, youtube_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE processed_files SET youtube_id = ? WHERE file_path = ?",
                (youtube_id, str(file_path)),
            )

    def get_youtube_id(self, file_path: Path) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT youtube_id FROM processed_files WHERE file_path = ?",
                (str(file_path),),
            ).fetchone()
        return row["youtube_id"] if row else None

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM processed_files").fetchone()[0]
            uploaded = conn.execute(
                "SELECT COUNT(*) FROM processed_files WHERE youtube_id IS NOT NULL"
            ).fetchone()[0]
        return {"total_tagged": total, "total_uploaded": uploaded}
