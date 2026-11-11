"""Small, inspectable local learning: memories, feedback, and routing examples.

This module never accesses the network and never modifies a generative model's
weights. A multinomial naive Bayes router is fitted from persisted labels when
needed; generative models receive retrieved memories through the orchestrator.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator
from uuid import uuid4


KINDS = ("task", "image", "video", "edit", "audio", "game", "voice", "animation")
_STOPWORDS = frozenset(
    "a an and are as at be by can could do for from have i in is it me my of on "
    "or please that the this to want with would you your".split()
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> list[str]:
    # Simple normalization keeps the router transparent and dependency-free.
    return [
        token
        for token in re.findall(r"[^\W_]+", text.casefold(), flags=re.UNICODE)
        if len(token) > 1 and token not in _STOPWORDS
    ][:4096]


def _prompt_key(prompt: str) -> str:
    normalized = " ".join(prompt.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _checked_text(text: str, name: str, maximum: int) -> str:
    if not isinstance(text, str):
        raise ValueError(f"{name} must be text.")
    cleaned = text.strip()
    if not cleaned:
        raise ValueError(f"{name} cannot be empty.")
    if len(cleaned) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters.")
    return cleaned


def _heuristic_route(prompt: str) -> dict[str, Any]:
    tokens = set(_tokens(prompt))
    # Editing verbs take precedence over the medium being edited.
    edits = {
        "edit", "editing", "crop", "resize", "rotate", "grayscale", "greyscale",
        "brighten", "brightness", "contrast", "sharpen", "retouch", "trim",
    }
    videos = {"video", "videos", "movie", "film", "animate", "animation", "clip", "slideshow"}
    images = {"image", "images", "picture", "pictures", "photo", "photograph", "illustration", "artwork", "poster", "draw", "paint"}
    audio = {"audio", "sound", "noise", "podcast", "voice", "music", "speech", "recording"}
    cleanup = {"clean", "cleanup", "denoise", "noise", "normalize", "normalise"}
    if (tokens & {"overlay", "overlays", "obs", "stinger", "stingers"}
            or "transparent" in tokens and tokens & {"animation", "animations", "animate", "animated"}):
        return {"kind": "animation", "confidence": 0.6, "learned": False}
    if tokens & audio and tokens & cleanup:
        return {"kind": "audio", "confidence": 0.6, "learned": False}
    if (tokens & {"pitch", "piper", "tts", "speak", "speech"}
            or {"say", "aloud"} <= tokens
            or tokens & {"voice", "voices"} and (
                not tokens & videos
                or tokens & {"change", "changing", "transform", "replace", "effect", "effects", "convert"}
            )):
        return {"kind": "voice", "confidence": 0.6, "learned": False}
    if tokens & audio and not tokens & videos:
        return {"kind": "audio", "confidence": 0.6, "learned": False}
    if tokens & edits:
        return {"kind": "edit", "confidence": 0.6, "learned": False}
    if tokens & videos:
        return {"kind": "video", "confidence": 0.6, "learned": False}
    if tokens & images:
        return {"kind": "image", "confidence": 0.6, "learned": False}
    if tokens & {"game", "games", "snake", "platformer", "shooter", "pong", "breakout"}:
        return {"kind": "game", "confidence": 0.6, "learned": False}
    return {"kind": "task", "confidence": 0.35, "learned": False}


class LearningStore:
    """SQLite-backed feedback and learning, safe to share with other tables.

    Each public operation opens its own connection. All table names start with
    ``learn_`` so a separate application store can share the database file.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS learn_memories (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS learn_memories_source ON learn_memories(source);
                CREATE TABLE IF NOT EXISTS learn_routes (
                    prompt_key TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    kind TEXT NOT NULL CHECK(kind IN ('task', 'image', 'video', 'edit', 'audio', 'game', 'voice', 'animation')),
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS learn_feedback (
                    id TEXT PRIMARY KEY,
                    job_id TEXT UNIQUE NOT NULL,
                    rating INTEGER NOT NULL CHECK(rating IN (-1, 1)),
                    note TEXT NOT NULL,
                    remember INTEGER NOT NULL,
                    correct_kind TEXT,
                    job_prompt TEXT NOT NULL,
                    job_kind TEXT NOT NULL,
                    job_status TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            # Preserve early installations whose route constraint predated
            # animation/voice/game workflows. No other application tables are touched.
            route_schema = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='learn_routes'").fetchone()[0]
            if "'animation'" not in route_schema:
                connection.executescript(
                    """
                    CREATE TABLE learn_routes_upgrade (
                        prompt_key TEXT PRIMARY KEY,
                        prompt TEXT NOT NULL,
                        kind TEXT NOT NULL CHECK(kind IN ('task', 'image', 'video', 'edit', 'audio', 'game', 'voice', 'animation')),
                        source TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    INSERT INTO learn_routes_upgrade SELECT * FROM learn_routes;
                    DROP TABLE learn_routes;
                    ALTER TABLE learn_routes_upgrade RENAME TO learn_routes;
                    """
                )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.db_path), timeout=15)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=15000")
            with connection:
                yield connection
        finally:
            connection.close()

    def add_memory(self, text: str, source: str = "user") -> dict[str, Any]:
        text = _checked_text(text, "Memory", 4000)
        source = _checked_text(source, "Source", 200)
        memory = {"id": str(uuid4()), "text": text, "source": source, "created_at": _now()}
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO learn_memories (id,text,source,created_at) VALUES (:id,:text,:source,:created_at)",
                memory,
            )
        return memory

    def list_memories(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM learn_memories ORDER BY created_at DESC, id")]

    def delete_memory(self, id: str) -> bool:
        with self._connect() as connection:
            return connection.execute("DELETE FROM learn_memories WHERE id=?", (id,)).rowcount > 0

    def relevant_memories(self, prompt: str, limit: int = 5) -> list[dict[str, Any]]:
        """Rank memories by TF-IDF cosine overlap; unrelated text stays out."""
        if not isinstance(prompt, str) or not isinstance(limit, int) or limit <= 0:
            return []
        memories = self.list_memories()
        query = Counter(_tokens(prompt))
        if not memories or not query:
            return []
        documents = [Counter(_tokens(memory["text"])) for memory in memories]
        frequency: Counter[str] = Counter()
        for document in documents:
            frequency.update(document.keys())
        count = len(documents)

        def weighted_vector(document: Counter[str]) -> dict[str, float]:
            return {
                token: (1 + math.log(frequency_in_document)) * (math.log((count + 1) / (frequency[token] + 1)) + 1)
                for token, frequency_in_document in document.items()
            }

        query_vector = weighted_vector(query)
        query_length = math.sqrt(sum(value * value for value in query_vector.values()))
        ranked: list[tuple[float, dict[str, Any]]] = []
        for memory, document in zip(memories, documents):
            vector = weighted_vector(document)
            length = math.sqrt(sum(value * value for value in vector.values()))
            dot = sum(query_vector.get(token, 0) * value for token, value in vector.items())
            score = dot / (query_length * length) if length and query_length else 0
            if score >= 0.05:
                ranked.append((score, memory))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [memory for _, memory in ranked[: min(limit, 20)]]

    def train_route(self, prompt: str, kind: str) -> None:
        prompt = _checked_text(prompt, "Prompt", 100000)
        if kind not in KINDS:
            raise ValueError("Route kind must be task, image, video, edit, audio, game, voice, or animation.")
        with self._connect() as connection:
            self._upsert_route(connection, prompt, kind, "explicit")

    @staticmethod
    def _upsert_route(connection: sqlite3.Connection, prompt: str, kind: str, source: str) -> None:
        connection.execute(
            """INSERT INTO learn_routes (prompt_key,prompt,kind,source,updated_at)
               VALUES (?,?,?,?,?) ON CONFLICT(prompt_key) DO UPDATE SET
               prompt=excluded.prompt,kind=excluded.kind,source=excluded.source,updated_at=excluded.updated_at""",
            (_prompt_key(prompt), prompt, kind, source, _now()),
        )

    def predict_route(self, prompt: str) -> dict[str, Any]:
        """Use supervised naive Bayes only with enough evidence and overlap.

        Confidence is a dispatch score, not a calibrated probability of success.
        Explicit choices in the app always override this automatic suggestion.
        """
        prompt = _checked_text(prompt, "Prompt", 100000)
        fallback = _heuristic_route(prompt)
        with self._connect() as connection:
            rows = connection.execute("SELECT prompt,kind FROM learn_routes").fetchall()
        labels = Counter(row["kind"] for row in rows)
        # A single class or a few examples must never hijack all new prompts.
        if len(rows) < 8 or len(labels) < 2:
            return fallback
        word_counts = {kind: Counter() for kind in KINDS}
        vocabulary: set[str] = set()
        for row in rows:
            counts = Counter(_tokens(row["prompt"]))
            bounded = {token: min(count, 3) for token, count in counts.items()}
            word_counts[row["kind"]].update(bounded)
            vocabulary.update(bounded)
        query_tokens = _tokens(prompt)
        query = Counter(token for token in query_tokens if token in vocabulary)
        if len(query) < 2 or not vocabulary or sum(query.values()) / max(len(query_tokens), 1) < 0.4:
            return fallback
        scores: dict[str, float] = {}
        for kind in KINDS:
            # Classes absent from the dataset cannot become learned predictions.
            if not labels[kind]:
                continue
            log_score = math.log((labels[kind] + 1) / (len(rows) + len(labels)))
            denominator = sum(word_counts[kind].values()) + len(vocabulary)
            for token, count in query.items():
                log_score += min(count, 3) * math.log((word_counts[kind][token] + 1) / denominator)
            scores[kind] = log_score
        maximum = max(scores.values())
        probabilities = {kind: math.exp(score - maximum) for kind, score in scores.items()}
        total = sum(probabilities.values())
        ranked = sorted(((value / total, kind) for kind, value in probabilities.items()), reverse=True)
        confidence, kind = ranked[0]
        margin = confidence - ranked[1][0]
        if labels[kind] >= 2 and confidence >= 0.70 and margin >= 0.25:
            return {"kind": kind, "confidence": round(confidence, 4), "learned": True}
        return fallback

    def record_feedback(
        self,
        job: dict[str, Any],
        rating: int,
        note: str = "",
        remember: bool = False,
        correct_kind: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(rating, bool) or rating not in (-1, 1):
            raise ValueError("Feedback rating must be 1 or -1.")
        if not isinstance(note, str) or len(note) > 4000:
            raise ValueError("Feedback note must be text of at most 4000 characters.")
        if correct_kind is not None and correct_kind not in KINDS:
            raise ValueError("Correct kind must be task, image, video, edit, audio, game, voice, or animation.")
        job_id = _checked_text(job.get("id", ""), "Job id", 200)
        prompt = _checked_text(job.get("prompt", ""), "Prompt", 100000)
        kind = job.get("kind", "task")
        status = job.get("status", "")
        if not isinstance(kind, str) or not isinstance(status, str):
            raise ValueError("Job kind and status must be text.")
        result = job.get("result")
        response = result.get("text", "") if isinstance(result, dict) else ""
        if not isinstance(response, str):
            response = ""
        note = note.strip()
        source = f"feedback:{job_id}"
        now = _now()
        memory_id: str | None = None
        route_trained = False
        with self._connect() as connection:
            previous = connection.execute("SELECT id,created_at FROM learn_feedback WHERE job_id=?", (job_id,)).fetchone()
            feedback_id = previous["id"] if previous else str(uuid4())
            connection.execute(
                """INSERT INTO learn_feedback
                   (id,job_id,rating,note,remember,correct_kind,job_prompt,job_kind,job_status,response_text,created_at,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET
                   rating=excluded.rating,note=excluded.note,remember=excluded.remember,
                   correct_kind=excluded.correct_kind,job_prompt=excluded.job_prompt,
                   job_kind=excluded.job_kind,job_status=excluded.job_status,
                   response_text=excluded.response_text,updated_at=excluded.updated_at""",
                (feedback_id, job_id, rating, note, int(bool(remember)), correct_kind, prompt, kind, status, response, now, now),
            )
            # Re-rating edits/retracts this feedback's memory instead of adding
            # another copy. A user can also delete it via delete_memory().
            existing_memory = connection.execute("SELECT id,created_at FROM learn_memories WHERE source=?", (source,)).fetchone()
            connection.execute("DELETE FROM learn_memories WHERE source=?", (source,))
            if remember and rating == 1 and status == "completed" and note:
                memory_id = existing_memory["id"] if existing_memory else str(uuid4())
                connection.execute(
                    "INSERT INTO learn_memories (id,text,source,created_at) VALUES (?,?,?,?)",
                    (memory_id, note, source, existing_memory["created_at"] if existing_memory else now),
                )
            # Remove only the old label from THIS feedback, not independent
            # explicit examples supplied by another job/user choice.
            connection.execute("DELETE FROM learn_routes WHERE prompt_key=? AND source=?", (_prompt_key(prompt), source))
            if correct_kind:
                # A negative rating can still contain a good routing correction;
                # it never turns the rejected output into a generative example.
                self._upsert_route(connection, prompt, correct_kind, source)
                route_trained = True
            elif rating == 1 and status == "completed" and kind in KINDS:
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO learn_routes (prompt_key,prompt,kind,source,updated_at) VALUES (?,?,?,?,?)",
                    (_prompt_key(prompt), prompt, kind, source, now),
                )
                route_trained = cursor.rowcount > 0
        return {
            "id": feedback_id,
            "job_id": job_id,
            "rating": rating,
            "note": note,
            "remember": bool(remember),
            "correct_kind": correct_kind,
            "memory_id": memory_id,
            "route_trained": route_trained,
            "learned": bool(memory_id or route_trained),
        }

    def stats(self) -> dict[str, int]:
        with self._connect() as connection:
            return {
                "memory_count": connection.execute("SELECT COUNT(*) FROM learn_memories").fetchone()[0],
                "feedback_count": connection.execute("SELECT COUNT(*) FROM learn_feedback").fetchone()[0],
                "route_examples": connection.execute("SELECT COUNT(*) FROM learn_routes").fetchone()[0],
            }

    def export_examples(self) -> str:
        """Export approved completed text answers, never images or raw files.

        This is a reviewable dataset export, not a fine-tuning operation.
        """
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT job_prompt,response_text FROM learn_feedback
                   WHERE rating=1 AND job_status='completed' AND trim(response_text) != ''
                   ORDER BY created_at,id"""
            ).fetchall()
        lines = []
        for row in rows:
            lines.append(json.dumps({"messages": [
                {"role": "system", "content": "You are Loom, an offline assistant. Follow the user's instructions."},
                {"role": "user", "content": row["job_prompt"]},
                {"role": "assistant", "content": row["response_text"]},
            ]}, ensure_ascii=False))
        return "\n".join(lines) + ("\n" if lines else "")
