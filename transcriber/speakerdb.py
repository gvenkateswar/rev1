"""Persistent store of known speakers and their voiceprints.

A voiceprint is a unit-norm speaker embedding (Resemblyzer, 256-d). We keep
*several* per speaker rather than one averaged vector: voices vary with mic,
room, and mood, so a centroid over many samples generalises much better than a
single recording, and keeping the samples lets the centroid be recomputed when
one is evicted.

Storage is SQLite (stdlib) at ``~/.transcriber/speakers.db``. This is biometric
data — see SPEC.md. It never leaves the machine, and :meth:`forget` really
deletes.
"""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Resemblyzer's VoiceEncoder output width. Vectors of another width are a bug
# (wrong encoder), not something to coerce, so we reject them on write.
EMBED_DIM = 256

# Keeping every sample forever lets a speaker's centroid drift toward whatever
# they were recorded on most often. 20 is enough to average out room and mic.
DEFAULT_MAX_SAMPLES = 20

_SCHEMA = """
CREATE TABLE IF NOT EXISTS speakers (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL UNIQUE,
    notes      TEXT    NOT NULL DEFAULT '',
    created_at REAL    NOT NULL,
    updated_at REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS voiceprints (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    speaker_id INTEGER NOT NULL REFERENCES speakers(id) ON DELETE CASCADE,
    vector     BLOB    NOT NULL,
    dim        INTEGER NOT NULL,
    source     TEXT    NOT NULL DEFAULT '',
    duration   REAL    NOT NULL DEFAULT 0.0,
    created_at REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_voiceprints_speaker
    ON voiceprints(speaker_id);
"""


@dataclass
class Speaker:
    """A known speaker and the centroid of their stored voiceprints."""

    id: int
    name: str
    centroid: np.ndarray
    sample_count: int
    notes: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


def default_db_path() -> Path:
    """Where the store lives. ``TRANSCRIBER_HOME`` overrides the directory."""
    home = os.environ.get("TRANSCRIBER_HOME")
    base = Path(home) if home else Path.home() / ".transcriber"
    return base / "speakers.db"


def normalize(vec: np.ndarray) -> np.ndarray:
    """Return *vec* scaled to unit length as float32.

    Cosine similarity is a plain dot product on unit vectors, so we normalise
    once on write and once on query instead of dividing on every comparison.
    """
    vec = np.asarray(vec, dtype=np.float32).ravel()
    norm = float(np.linalg.norm(vec))
    if norm == 0.0:
        raise ValueError("Cannot normalize a zero vector (silent audio?)")
    return (vec / norm).astype(np.float32)


class SpeakerStore:
    """SQLite-backed speaker store.

    Usable as a context manager::

        with SpeakerStore() as store:
            store.enroll("Priya", voiceprint, source="meeting1.wav")
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        max_samples: int = DEFAULT_MAX_SAMPLES,
    ) -> None:
        self.path = Path(path) if path is not None else default_db_path()
        self.max_samples = max_samples
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        # Not on by default in SQLite; without it, deleting a speaker would
        # orphan their voiceprints instead of cascading.
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def __enter__(self) -> "SpeakerStore":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def enroll(
        self,
        name: str,
        voiceprint: np.ndarray,
        *,
        source: str = "",
        duration: float = 0.0,
    ) -> Speaker:
        """Add a voiceprint for *name*, creating the speaker if new.

        Re-enrolling an existing name appends a sample and sharpens their
        centroid; it does not overwrite what is already known about them.
        """
        name = name.strip()
        if not name:
            raise ValueError("Speaker name cannot be empty")

        vec = normalize(voiceprint)
        if vec.size != EMBED_DIM:
            raise ValueError(
                f"Expected a {EMBED_DIM}-d voiceprint, got {vec.size}-d. "
                "This usually means a different speaker encoder produced it."
            )

        now = time.time()
        cur = self._conn.execute(
            "SELECT id FROM speakers WHERE name = ?", (name,)
        ).fetchone()
        if cur is None:
            cur = self._conn.execute(
                "INSERT INTO speakers (name, notes, created_at, updated_at) "
                "VALUES (?, '', ?, ?)",
                (name, now, now),
            )
            speaker_id = int(cur.lastrowid)
        else:
            speaker_id = int(cur["id"])
            self._conn.execute(
                "UPDATE speakers SET updated_at = ? WHERE id = ?", (now, speaker_id)
            )

        self._conn.execute(
            "INSERT INTO voiceprints "
            "(speaker_id, vector, dim, source, duration, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (speaker_id, vec.tobytes(), int(vec.size), source, float(duration), now),
        )
        self._prune_samples(speaker_id)
        self._conn.commit()
        return self.get(name)

    def rename(self, old_name: str, new_name: str) -> Speaker:
        """Rename a speaker, keeping their voiceprints."""
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Speaker name cannot be empty")
        row = self._conn.execute(
            "SELECT id FROM speakers WHERE name = ?", (old_name,)
        ).fetchone()
        if row is None:
            raise KeyError(f"No such speaker: {old_name!r}")
        clash = self._conn.execute(
            "SELECT id FROM speakers WHERE name = ? AND id != ?",
            (new_name, int(row["id"])),
        ).fetchone()
        if clash is not None:
            raise ValueError(
                f"A different speaker is already named {new_name!r}. "
                "Merge them manually or pick another name."
            )
        self._conn.execute(
            "UPDATE speakers SET name = ?, updated_at = ? WHERE id = ?",
            (new_name, time.time(), int(row["id"])),
        )
        self._conn.commit()
        return self.get(new_name)

    def forget(self, name: str) -> None:
        """Delete a speaker and every voiceprint of theirs."""
        row = self._conn.execute(
            "SELECT id FROM speakers WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise KeyError(f"No such speaker: {name!r}")
        # Explicit child delete: PRAGMA foreign_keys can be off on some builds,
        # and a half-deleted speaker leaves matchable orphan voiceprints.
        self._conn.execute(
            "DELETE FROM voiceprints WHERE speaker_id = ?", (int(row["id"]),)
        )
        self._conn.execute("DELETE FROM speakers WHERE id = ?", (int(row["id"]),))
        self._conn.commit()

    def _prune_samples(self, speaker_id: int) -> None:
        """Keep only the newest ``max_samples`` voiceprints for a speaker."""
        self._conn.execute(
            "DELETE FROM voiceprints WHERE speaker_id = ? AND id NOT IN ("
            "  SELECT id FROM voiceprints WHERE speaker_id = ? "
            "  ORDER BY created_at DESC, id DESC LIMIT ?"
            ")",
            (speaker_id, speaker_id, self.max_samples),
        )

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get(self, name: str) -> Speaker:
        row = self._conn.execute(
            "SELECT * FROM speakers WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise KeyError(f"No such speaker: {name!r}")
        return self._build_speaker(row)

    def all_speakers(self) -> list[Speaker]:
        """Every speaker with at least one usable voiceprint, by name.

        A speaker whose samples are all unreadable is skipped rather than
        raising: one corrupt row should not break transcription of a file.
        """
        rows = self._conn.execute("SELECT * FROM speakers ORDER BY name").fetchall()
        out: list[Speaker] = []
        for row in rows:
            speaker = self._build_speaker(row)
            if speaker.sample_count:
                out.append(speaker)
        return out

    def _build_speaker(self, row: sqlite3.Row) -> Speaker:
        vectors = self._vectors_for(int(row["id"]))
        if vectors:
            stacked = np.vstack(vectors)
            mean = stacked.mean(axis=0)
            # A centroid of near-opposite vectors can cancel to ~zero; that
            # speaker is unmatchable rather than an error, so fall back to a
            # zero vector, which scores 0 against everything.
            try:
                centroid = normalize(mean)
            except ValueError:
                centroid = np.zeros(EMBED_DIM, dtype=np.float32)
        else:
            centroid = np.zeros(EMBED_DIM, dtype=np.float32)
        return Speaker(
            id=int(row["id"]),
            name=str(row["name"]),
            centroid=centroid,
            sample_count=len(vectors),
            notes=str(row["notes"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    def _vectors_for(self, speaker_id: int) -> list[np.ndarray]:
        rows = self._conn.execute(
            "SELECT vector, dim FROM voiceprints WHERE speaker_id = ? "
            "ORDER BY created_at DESC, id DESC",
            (speaker_id,),
        ).fetchall()
        vectors: list[np.ndarray] = []
        for row in rows:
            # Guard the invariant rather than trusting the blob. A truncated
            # write fails here (frombuffer rejects a length that is not a
            # whole number of float32s) or fails the size check below; either
            # way one bad row is skipped instead of breaking every speaker.
            try:
                vec = np.frombuffer(row["vector"], dtype=np.float32)
            except ValueError:
                continue
            if vec.size != int(row["dim"]) or vec.size != EMBED_DIM:
                continue
            vectors.append(vec)
        return vectors
