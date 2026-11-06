
from app.database.db import get_connection, initialize_database


class TaskManager:

    def __init__(self, db_path=None):
        self.db_path = db_path
        initialize_database(self.db_path)

    def create_task(self, title, description=""):
        title = title.strip()
        description = description.strip()

        if not title:
            raise ValueError("Task title cannot be empty.")

        with get_connection(self.db_path) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO tasks (title, description)
                    VALUES (?, ?)
                    """,
                    (title, description),
                )

                return cursor.lastrowid

    def list_tasks(self, status="all"):
        if status not in ("all", "pending", "completed"):
            raise ValueError("Invalid task status.")

        with get_connection(self.db_path) as connection:
            if status == "all":
                rows = connection.execute(
                    "SELECT * FROM tasks ORDER BY id DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM tasks
                    WHERE status = ?
                    ORDER BY id DESC
                    """,
                    (status,),
                ).fetchall()

        return [dict(row) for row in rows]

    def complete_task(self, task_id):
        with get_connection(self.db_path) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE tasks
                    SET status = 'completed',
                        completed_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'pending'
                    """,
                    (task_id,),
                )

                return cursor.rowcount > 0

    def delete_task(self, task_id):
        with get_connection(self.db_path) as connection:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM tasks WHERE id = ?",
                    (task_id,),
                )

                return cursor.rowcount > 0
