
import sqlite3
from contextlib import contextmanager
from pathlib import Path


DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "tasks.db"
)


@contextmanager
def get_connection(db_path=None):
    database_path = Path(db_path) if db_path else DEFAULT_DB_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row

    try:
        yield connection
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
