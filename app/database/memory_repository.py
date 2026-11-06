import re
from datetime import datetime, timedelta, timezone

from app.database.db import get_connection


MAX_MEMORY_CONTENT_LENGTH = 2000
MAX_RETRIEVED_MEMORIES = 5
MAX_RETRIEVED_MEMORY_CHARACTERS = 2000
ALLOWED_MEMORY_CATEGORIES = {
    "fact",
    "instruction",
    "preference",
    "project",
    "routine",
}

_UNSET = object()
_WORD_PATTERN = re.compile(r"[^\W_]+")
_QUERY_STOP_WORDS = {
    "about",
    "after",
    "all",
    "and",
    "are",
    "can",
    "could",
    "for",
    "from",
    "how",
    "into",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "please",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "you",
    "your",
}


class MemoryRepositoryError(ValueError):
    """Raised when memory data cannot be safely created or updated."""


class MemoryNotFoundError(MemoryRepositoryError):
    """Raised when an update targets a memory that does not exist."""


class MemoryConflictError(MemoryRepositoryError):
    """Raised when a memory changed since it was read."""


class DuplicateMemoryError(MemoryRepositoryError):
    """Raised when an update would duplicate another memory."""


class MemoryRepository:

    def __init__(self, db_path=None):
        self.db_path = db_path
        self.initialize()

    def initialize(self):
        with get_connection(self.db_path) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        content TEXT NOT NULL,
                        category TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

    def create_memory(self, content, category=None):
        memory_id, _ = self.create_memory_with_status(content, category)
        return memory_id

    def create_memory_with_status(self, content, category=None):
        content = self._validate_content(content)
        category = self._validate_category(category)
        duplicate_key = self._duplicate_key(content)

        with get_connection(self.db_path) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                rows = connection.execute(
                    "SELECT id, content FROM memories ORDER BY id",
                ).fetchall()
                for row in rows:
                    if self._duplicate_key(row["content"]) == duplicate_key:
                        return row["id"], False

                cursor = connection.execute(
                    """
                    INSERT INTO memories (content, category)
                    VALUES (?, ?)
                    """,
                    (content, category),
                )
                return cursor.lastrowid, True

    def get_memory(self, memory_id):
        memory_id = self._validate_memory_id(memory_id)
        with get_connection(self.db_path) as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()

        return dict(row) if row is not None else None

    def list_memories(self):
        with get_connection(self.db_path) as connection:
            rows = connection.execute(
                "SELECT * FROM memories ORDER BY id",
            ).fetchall()

        return [dict(row) for row in rows]

    def retrieve_relevant_memories(self, query):
        if not isinstance(query, str) or not query.strip():
            return []

        query_terms = {
            term
            for term in _WORD_PATTERN.findall(query.casefold())
            if len(term) > 1 and term not in _QUERY_STOP_WORDS
        }
        if not query_terms:
            return []

        candidates = []
        for memory in self.list_memories():
            content_terms = set(
                _WORD_PATTERN.findall(memory["content"].casefold())
            )
            matching_terms = query_terms & content_terms
            category_match = (
                memory["category"] in query_terms
                if memory["category"] is not None
                else False
            )
            score = len(matching_terms) + (2 if category_match else 0)
            if score:
                candidates.append(
                    (
                        -score,
                        memory["id"],
                        memory,
                    )
                )

        candidates.sort(key=lambda candidate: (candidate[0], candidate[1]))
        selected = []
        characters_used = 0
        for _, _, memory in candidates:
            if len(selected) >= MAX_RETRIEVED_MEMORIES:
                break

            memory_size = len(memory["content"])
            if characters_used + memory_size > MAX_RETRIEVED_MEMORY_CHARACTERS:
                continue

            selected.append(memory)
            characters_used += memory_size

        return selected

    def update_memory(
        self,
        memory_id,
        *,
        content=_UNSET,
        category=_UNSET,
        expected_updated_at=_UNSET,
    ):
        memory_id = self._validate_memory_id(memory_id)
        if content is _UNSET and category is _UNSET:
            raise MemoryRepositoryError(
                "At least one memory field must be provided."
            )
        if expected_updated_at is not _UNSET and not isinstance(
            expected_updated_at,
            str,
        ):
            raise MemoryRepositoryError(
                "Expected memory version must be a timestamp string."
            )

        with get_connection(self.db_path) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM memories WHERE id = ?",
                    (memory_id,),
                ).fetchone()
                if row is None:
                    raise MemoryNotFoundError(
                        f"Memory {memory_id} was not found."
                    )
                if (
                    expected_updated_at is not _UNSET
                    and row["updated_at"] != expected_updated_at
                ):
                    raise MemoryConflictError(
                        f"Memory {memory_id} changed since it was loaded."
                    )

                new_content = (
                    row["content"]
                    if content is _UNSET
                    else self._validate_content(content)
                )
                new_category = (
                    row["category"]
                    if category is _UNSET
                    else self._validate_category(category)
                )

                other_rows = connection.execute(
                    "SELECT id, content FROM memories WHERE id != ?",
                    (memory_id,),
                ).fetchall()
                duplicate_key = self._duplicate_key(new_content)
                if any(
                    self._duplicate_key(other["content"]) == duplicate_key
                    for other in other_rows
                ):
                    raise DuplicateMemoryError(
                        "Another memory already has identical content."
                    )

                if (
                    new_content != row["content"]
                    or new_category != row["category"]
                ):
                    updated_at = self._next_updated_at(row["updated_at"])
                    update_sql = """
                        UPDATE memories
                        SET content = ?, category = ?, updated_at = ?
                        WHERE id = ?
                    """
                    parameters = (
                        new_content,
                        new_category,
                        updated_at,
                        memory_id,
                    )
                    if expected_updated_at is not _UNSET:
                        update_sql += " AND updated_at = ?"
                        parameters += (expected_updated_at,)
                    cursor = connection.execute(
                        update_sql,
                        parameters,
                    )
                    if cursor.rowcount == 0:
                        raise MemoryConflictError(
                            f"Memory {memory_id} changed during the update."
                        )

                updated_row = connection.execute(
                    "SELECT * FROM memories WHERE id = ?",
                    (memory_id,),
                ).fetchone()

        return dict(updated_row)

    def delete_memory_if_unchanged(
        self,
        memory_id,
        *,
        expected_content,
        expected_category,
        expected_updated_at,
    ):
        memory_id = self._validate_memory_id(memory_id)
        if not isinstance(expected_content, str):
            raise MemoryRepositoryError(
                "Expected memory content must be text."
            )
        if (
            expected_category is not None
            and not isinstance(expected_category, str)
        ):
            raise MemoryRepositoryError(
                "Expected memory category must be text or null."
            )
        if not isinstance(expected_updated_at, str):
            raise MemoryRepositoryError(
                "Expected memory version must be a timestamp string."
            )

        with get_connection(self.db_path) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    DELETE FROM memories
                    WHERE id = ?
                      AND content = ?
                      AND category IS ?
                      AND updated_at = ?
                    """,
                    (
                        memory_id,
                        expected_content,
                        expected_category,
                        expected_updated_at,
                    ),
                )
                if cursor.rowcount > 0:
                    return True

                current = connection.execute(
                    "SELECT 1 FROM memories WHERE id = ?",
                    (memory_id,),
                ).fetchone()
                if current is None:
                    raise MemoryNotFoundError(
                        f"Memory {memory_id} was not found."
                    )
                raise MemoryConflictError(
                    f"Memory {memory_id} changed since deletion was requested."
                )

    def delete_memory(self, memory_id):
        memory_id = self._validate_memory_id(memory_id)
        with get_connection(self.db_path) as connection:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM memories WHERE id = ?",
                    (memory_id,),
                )

        return cursor.rowcount > 0

    @staticmethod
    def _validate_memory_id(memory_id):
        if (
            isinstance(memory_id, bool)
            or not isinstance(memory_id, int)
            or memory_id <= 0
        ):
            raise MemoryRepositoryError(
                "Memory ID must be a positive integer."
            )
        return memory_id

    @staticmethod
    def _validate_content(content):
        if not isinstance(content, str):
            raise MemoryRepositoryError("Memory content must be text.")

        content = content.strip()
        if not content:
            raise MemoryRepositoryError("Memory content cannot be empty.")
        if len(content) > MAX_MEMORY_CONTENT_LENGTH:
            raise MemoryRepositoryError(
                "Memory content cannot exceed "
                f"{MAX_MEMORY_CONTENT_LENGTH} characters."
            )
        return content

    @staticmethod
    def _validate_category(category):
        if category is None:
            return None
        if not isinstance(category, str):
            raise MemoryRepositoryError("Memory category must be text.")

        category = category.strip().lower()
        if not category:
            return None
        if category not in ALLOWED_MEMORY_CATEGORIES:
            allowed = ", ".join(sorted(ALLOWED_MEMORY_CATEGORIES))
            raise MemoryRepositoryError(
                f"Memory category must be one of: {allowed}."
            )
        return category

    @staticmethod
    def _duplicate_key(content):
        return " ".join(content.casefold().split())

    @staticmethod
    def _next_updated_at(current_value):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        current = datetime.fromisoformat(current_value)
        if now <= current:
            now = current + timedelta(microseconds=1)
        return now.strftime("%Y-%m-%d %H:%M:%S.%f")
