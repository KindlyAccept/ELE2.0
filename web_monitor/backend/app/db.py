from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import threading
import time
import uuid
from typing import List, Dict, Tuple


class DialogueDB:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = threading.Lock()

    def init(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    started_at REAL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS dialogues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp REAL,
                    emotion_label TEXT,
                    valence REAL,
                    arousal REAL,
                    dominance REAL
                )
                """
            )
            self._conn.commit()

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (id, started_at) VALUES (?, ?)",
                (session_id, time.time()),
            )
            self._conn.commit()
        return session_id

    def insert_dialogue(
        self,
        session_id: str,
        role: str,
        content: str,
        timestamp: float,
        emotion_label: str | None = None,
        valence: float | None = None,
        arousal: float | None = None,
        dominance: float | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO dialogues (
                    session_id, role, content, timestamp,
                    emotion_label, valence, arousal, dominance
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    timestamp,
                    emotion_label,
                    valence,
                    arousal,
                    dominance,
                ),
            )
            self._conn.commit()

    def list_dialogue(self, session_id: str) -> List[Dict]:
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT role, content, timestamp, emotion_label, valence, arousal, dominance
                FROM dialogues
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (session_id,),
            )
            rows = cursor.fetchall()
        return [
            {
                "role": row[0],
                "content": row[1],
                "timestamp": row[2],
                "emotion_label": row[3],
                "valence": row[4],
                "arousal": row[5],
                "dominance": row[6],
            }
            for row in rows
        ]

    def clear_dialogue(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM dialogues WHERE session_id = ?",
                (session_id,),
            )
            self._conn.commit()

    def export_dialogue(self, session_id: str, fmt: str) -> Tuple[str, str]:
        data = self.list_dialogue(session_id)
        if fmt == "csv":
            output = io.StringIO()
            fieldnames = [
                "role",
                "content",
                "timestamp",
                "emotion_label",
                "valence",
                "arousal",
                "dominance",
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
            csv_data = output.getvalue()
            return "text/csv", csv_data
        json_data = json.dumps(data, ensure_ascii=False)
        return "application/json", json_data
