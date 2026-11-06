
import json

from app.database.db import get_connection


class ConversationRepository:

    def initialize(self):
        with get_connection() as connection:
            with connection:
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
        if not isinstance(history, list):
            raise ValueError("History must be a list.")

        history_json = json.dumps(history)

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

        return json.loads(row["history_json"])

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
                connection.execute("PRAGMA foreign_keys = ON")

                cursor = connection.execute(
                    "DELETE FROM conversations WHERE id = ?",
                    (conversation_id,)
                )

                return cursor.rowcount > 0
