
import json

from app.database.db import (
    get_connection,
    has_unique_conversation_message_index,
)


class ConversationRepositoryError(ValueError):
    """Raised when conversation data cannot be safely read or saved."""


class ConversationMigrationError(ConversationRepositoryError):
    """Raised when legacy conversation data cannot be migrated safely."""


class ConversationRepository:

    def initialize(self):
        with get_connection(
            backup_before_conversation_migration=True
        ) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")

                connection.execute("""
                    CREATE TABLE IF NOT EXISTS conversations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL DEFAULT 'New Conversation',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                connection.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id INTEGER NOT NULL,
                        history_json TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (conversation_id)
                            REFERENCES conversations(id)
                            ON DELETE CASCADE
                    )
                """)

                duplicate_conversations = connection.execute(
                    """
                    SELECT conversation_id, COUNT(*) AS row_count
                    FROM conversation_messages
                    GROUP BY conversation_id
                    HAVING COUNT(*) > 1
                    ORDER BY conversation_id
                    """
                ).fetchall()

                for duplicate in duplicate_conversations:
                    rows = connection.execute(
                        """
                        SELECT id, history_json
                        FROM conversation_messages
                        WHERE conversation_id = ?
                        ORDER BY updated_at DESC, id DESC
                        """,
                        (duplicate["conversation_id"],),
                    ).fetchall()

                    histories = set()
                    for row in rows:
                        try:
                            history = json.loads(row["history_json"])
                        except (json.JSONDecodeError, TypeError) as error:
                            raise ConversationRepositoryError(
                                "Stored history for conversation "
                                f"{duplicate['conversation_id']} contains "
                                "malformed JSON."
                            ) from error

                        try:
                            self._validate_history(history)
                        except ConversationRepositoryError as error:
                            raise ConversationRepositoryError(
                                "Stored history for conversation "
                                f"{duplicate['conversation_id']} is invalid: "
                                f"{error}"
                            ) from error

                        histories.add(
                            json.dumps(
                                history,
                                sort_keys=True,
                                separators=(",", ":"),
                                ensure_ascii=False,
                            )
                        )

                    if len(histories) > 1:
                        raise ConversationMigrationError(
                            "Cannot migrate conversation "
                            f"{duplicate['conversation_id']}: it has "
                            f"{duplicate['row_count']} conflicting message "
                            "histories. No histories were discarded."
                        )

                    connection.execute(
                        """
                        DELETE FROM conversation_messages
                        WHERE conversation_id = ? AND id != ?
                        """,
                        (duplicate["conversation_id"], rows[0]["id"]),
                    )

                connection.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS
                        idx_conversation_messages_conversation_id
                    ON conversation_messages (conversation_id)
                    """
                )

                if not has_unique_conversation_message_index(connection):
                    raise ConversationMigrationError(
                        "Could not enforce one message history per "
                        "conversation."
                    )

    def __init__(self):
        self.initialize()

    def create_conversation(self, title="New Conversation"):
        with get_connection() as connection:
            with connection:
                cursor = connection.execute(
                    "INSERT INTO conversations (title) VALUES (?)",
                    (title,)
                )

                conversation_id = cursor.lastrowid

                connection.execute(
                    """
                    INSERT INTO conversation_messages
                    (conversation_id, history_json)
                    VALUES (?, ?)
                    """,
                    (conversation_id, "[]")
                )

        return conversation_id

    def save_history(self, conversation_id, history):
        self._validate_history(history)

        try:
            history_json = json.dumps(history)
        except (TypeError, ValueError, RecursionError) as error:
            raise ConversationRepositoryError(
                "History could not be serialized as JSON."
            ) from error

        with get_connection() as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE conversation_messages
                    SET history_json = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE conversation_id = ?
                    """,
                    (history_json, conversation_id)
                )

                if cursor.rowcount == 0:
                    raise ValueError("Conversation not found.")

                connection.execute(
                    """
                    UPDATE conversations
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (conversation_id,)
                )

                first_user_message = next(
                    (
                        item["content"]
                        for item in history
                        if item.get("role") == "user"
                        and isinstance(item.get("content"), str)
                    ),
                    None
                )

                if first_user_message:
                    title = first_user_message[:60]

                    connection.execute(
                        """
                        UPDATE conversations
                        SET title = ?
                        WHERE id = ?
                        AND title = 'New Conversation'
                        """,
                        (title, conversation_id)
                    )

    def get_history(self, conversation_id):
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT cm.history_json
                FROM conversation_messages cm
                JOIN conversations c
                    ON c.id = cm.conversation_id
                WHERE c.id = ?
                """,
                (conversation_id,)
            ).fetchone()

        if row is None:
            return None

        try:
            history = json.loads(row["history_json"])
        except (json.JSONDecodeError, TypeError) as error:
            raise ConversationRepositoryError(
                f"Stored history for conversation {conversation_id} "
                "contains malformed JSON."
            ) from error

        try:
            self._validate_history(history)
        except ConversationRepositoryError as error:
            raise ConversationRepositoryError(
                f"Stored history for conversation {conversation_id} "
                f"is invalid: {error}"
            ) from error

        return history

    @staticmethod
    def _validate_history(history):
        if not isinstance(history, list):
            raise ConversationRepositoryError("History must be a list.")

        for index, message in enumerate(history):
            if not isinstance(message, dict):
                raise ConversationRepositoryError(
                    f"History message {index} must be an object."
                )

            role = message.get("role")
            if not isinstance(role, str) or not role.strip():
                raise ConversationRepositoryError(
                    f"History message {index} must have a non-empty role."
                )

            if "content" not in message or (
                message["content"] is not None
                and not isinstance(message["content"], str)
            ):
                raise ConversationRepositoryError(
                    f"History message {index} must have text or null content."
                )

        return history

    def list_conversations(self):
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def delete_conversation(self, conversation_id):
        with get_connection() as connection:
            with connection:

                cursor = connection.execute(
                    "DELETE FROM conversations WHERE id = ?",
                    (conversation_id,)
                )

                return cursor.rowcount > 0
