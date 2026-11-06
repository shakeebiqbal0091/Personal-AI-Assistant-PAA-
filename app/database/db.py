
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path


DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "tasks.db"
)


def has_unique_conversation_message_index(connection):
    table_exists = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'conversation_messages'
        """
    ).fetchone()

    if table_exists is None:
        return False

    for index in connection.execute(
        "PRAGMA index_list(conversation_messages)"
    ).fetchall():
        if not index["unique"] or index["partial"]:
            continue

        escaped_name = index["name"].replace('"', '""')
        columns = connection.execute(
            f'PRAGMA index_info("{escaped_name}")'
        ).fetchall()

        if [column["name"] for column in columns] == ["conversation_id"]:
            return True

    return False


def _needs_conversation_message_migration(connection):
    tables = {
        row["name"]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()
    }

    return (
        "conversations" not in tables
        or "conversation_messages" not in tables
        or not has_unique_conversation_message_index(connection)
    )


def _backup_database(connection, database_path):
    descriptor, backup_name = tempfile.mkstemp(
        prefix=f"{database_path.name}.pre-migration-",
        suffix=".sqlite3",
        dir=database_path.parent,
    )
    os.close(descriptor)
    backup_path = Path(backup_name)

    try:
        backup_connection = sqlite3.connect(backup_path)
        try:
            connection.backup(backup_connection)
        finally:
            backup_connection.close()
    except Exception as error:
        try:
            backup_path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            raise RuntimeError(
                "Database backup failed and its incomplete file could not "
                f"be removed: {backup_path}"
            ) from cleanup_error

        raise RuntimeError(
            f"Could not back up the database before migration: {backup_path}"
        ) from error

    return backup_path


@contextmanager
def get_connection(db_path=None, *, backup_before_conversation_migration=False):
    database_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)

    database_existed = database_path.exists()
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row

    try:
        migration_required = (
            backup_before_conversation_migration
            and database_existed
            and _needs_conversation_message_migration(connection)
        )
        if migration_required:
            _backup_database(connection, database_path)

        # Per-connection: FK enforcement is OFF by default in SQLite.
        connection.execute("PRAGMA foreign_keys = ON")
        if not migration_required:
            # Persistent on the file; lets Streamlit/FastAPI read while writing.
            connection.execute("PRAGMA journal_mode = WAL")
        yield connection
        if migration_required:
            # A failed migration leaves the database's journal mode unchanged.
            connection.execute("PRAGMA journal_mode = WAL")
    finally:
        connection.close()

def initialize_database(db_path=None):
    with get_connection(db_path) as connection:
        with connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
