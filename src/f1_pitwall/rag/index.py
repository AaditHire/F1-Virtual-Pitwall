"""SQLite FTS5 retrieval with source and temporal metadata."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class KnowledgeHit(BaseModel):
    """One local full-text retrieval result."""

    model_config = ConfigDict(frozen=True)

    source: str
    title: str
    content: str
    season: int | None
    available_at: str | None
    score: float


class LocalKnowledgeIndex:
    """Small, dependency-free RAG store for documents we may legally retain."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        """Create the FTS table if it does not exist."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                """
                    CREATE VIRTUAL TABLE IF NOT EXISTS knowledge USING fts5(
                        source UNINDEXED,
                        title,
                        content,
                        season UNINDEXED,
                        available_at UNINDEXED
                    )
                """
            )

    def add_document(
        self,
        *,
        source: str,
        title: str,
        content: str,
        season: int | None = None,
        available_at: str | None = None,
    ) -> None:
        """Index one document with provenance and availability metadata."""
        self.initialize()
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("DELETE FROM knowledge WHERE source = ?", (source,))
            connection.execute(
                "INSERT INTO knowledge(source, title, content, season, available_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, title, content, season, available_at),
            )

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        season: int | None = None,
        available_before: str | None = None,
    ) -> tuple[KnowledgeHit, ...]:
        """Search locally while enforcing optional temporal filters."""
        self.initialize()
        tokens = re.findall(r"\w+", query.casefold())
        if not tokens:
            return ()
        safe_query = " ".join(f'"{token}"' for token in tokens)
        select = """
            SELECT source, title, content, season, available_at, bm25(knowledge)
            FROM knowledge
        """
        if season is not None and available_before is not None:
            sql = (
                select
                + """
                WHERE knowledge MATCH ? AND season = ?
                    AND (available_at IS NULL OR available_at <= ?)
                ORDER BY bm25(knowledge) LIMIT ?
            """
            )
            parameters: list[object] = [safe_query, season, available_before, limit]
        elif season is not None:
            sql = (
                select
                + """
                WHERE knowledge MATCH ? AND season = ?
                ORDER BY bm25(knowledge) LIMIT ?
            """
            )
            parameters = [safe_query, season, limit]
        elif available_before is not None:
            sql = (
                select
                + """
                WHERE knowledge MATCH ? AND (available_at IS NULL OR available_at <= ?)
                ORDER BY bm25(knowledge) LIMIT ?
            """
            )
            parameters = [safe_query, available_before, limit]
        else:
            sql = (
                select
                + """
                WHERE knowledge MATCH ? ORDER BY bm25(knowledge) LIMIT ?
            """
            )
            parameters = [safe_query, limit]
        with closing(sqlite3.connect(self.database_path)) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return tuple(
            KnowledgeHit(
                source=row[0],
                title=row[1],
                content=row[2],
                season=int(row[3]) if row[3] is not None else None,
                available_at=row[4],
                score=float(row[5]),
            )
            for row in rows
        )
