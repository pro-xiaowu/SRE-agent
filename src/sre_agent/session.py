from __future__ import annotations

from collections import defaultdict
from typing import Protocol


class SessionStore(Protocol):
    def create_session(self, session_id: str, title: str = "新会话") -> None: ...
    def list_sessions(self) -> list[dict]: ...
    def delete_session(self, session_id: str) -> None: ...
    def history(self, session_id: str, limit: int = 10) -> list[tuple[str, str]]: ...
    def append(self, session_id: str, role: str, content: str) -> None: ...
    def clarification_count(self, session_id: str) -> int: ...
    def incr_clarification(self, session_id: str) -> int: ...
    def reset_clarification(self, session_id: str) -> None: ...


class MemorySessionStore:
    def __init__(self) -> None:
        self._messages: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._clarifications: dict[str, int] = defaultdict(int)
        self._sessions: dict[str, str] = {}

    def create_session(self, session_id: str, title: str = "新会话") -> None:
        self._sessions.setdefault(session_id, title or "新会话")

    def list_sessions(self) -> list[dict]:
        result = []
        for session_id, title in self._sessions.items():
            result.append(
                {
                    "id": session_id,
                    "title": title,
                    "message_count": len(self._messages[session_id]),
                }
            )
        return result

    def delete_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._messages.pop(session_id, None)
        self._clarifications.pop(session_id, None)

    def history(self, session_id: str, limit: int = 10) -> list[tuple[str, str]]:
        return self._messages[session_id][-limit:]

    def append(self, session_id: str, role: str, content: str) -> None:
        self.create_session(session_id, content[:40] if role == "human" else "新会话")
        self._messages[session_id].append((role, content))

    def clarification_count(self, session_id: str) -> int:
        return self._clarifications[session_id]

    def incr_clarification(self, session_id: str) -> int:
        self._clarifications[session_id] += 1
        return self._clarifications[session_id]

    def reset_clarification(self, session_id: str) -> None:
        self._clarifications[session_id] = 0


class PostgresSessionStore:
    def __init__(self, database_url: str) -> None:
        from sre_agent.db import connect, init_schema

        self._conn = connect(database_url)
        init_schema(self._conn)

    def create_session(self, session_id: str, title: str = "新会话") -> None:
        self._conn.execute(
            "INSERT INTO sessions (id, title) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (session_id, title or "新会话"),
        )

    def list_sessions(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT s.id, s.title, s.updated_at, COUNT(m.id) AS message_count "
            "FROM sessions s LEFT JOIN messages m ON m.session_id=s.id "
            "GROUP BY s.id ORDER BY s.updated_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM messages WHERE session_id=%s", (session_id,))
        self._conn.execute("DELETE FROM clarifications WHERE session_id=%s", (session_id,))
        self._conn.execute("DELETE FROM sessions WHERE id=%s", (session_id,))

    def history(self, session_id: str, limit: int = 10) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT role, content FROM messages WHERE session_id=%s ORDER BY id DESC LIMIT %s",
            (session_id, limit),
        ).fetchall()
        return [(r["role"], r["content"]) for r in reversed(rows)]

    def append(self, session_id: str, role: str, content: str) -> None:
        self.create_session(session_id, content[:40] if role == "human" else "新会话")
        self._conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
            (session_id, role, content),
        )
        self._conn.execute("UPDATE sessions SET updated_at=now() WHERE id=%s", (session_id,))

    def clarification_count(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT n FROM clarifications WHERE session_id=%s", (session_id,)
        ).fetchone()
        return 0 if row is None else int(row["n"])

    def incr_clarification(self, session_id: str) -> int:
        row = self._conn.execute(
            "INSERT INTO clarifications (session_id, n) VALUES (%s, 1) "
            "ON CONFLICT (session_id) DO UPDATE SET n = clarifications.n + 1 RETURNING n",
            (session_id,),
        ).fetchone()
        return int(row["n"])

    def reset_clarification(self, session_id: str) -> None:
        self._conn.execute(
            "INSERT INTO clarifications (session_id, n) VALUES (%s, 0) "
            "ON CONFLICT (session_id) DO UPDATE SET n = 0",
            (session_id,),
        )


def build_session_store(database_url: str | None):
    if not database_url:
        return MemorySessionStore()
    return PostgresSessionStore(database_url)
