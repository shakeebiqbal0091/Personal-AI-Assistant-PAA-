
import json
import shutil
import sqlite3

import pytest

from app.database import db
from app.database.conversation_repository import (
    ConversationMigrationError,
    ConversationRepository,
    ConversationRepositoryError,
)


@pytest.fixture
def repository(tmp_path, monkeypatch):
    db_path = tmp_path / "test_conversations.db"
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", db_path)

    return ConversationRepository()


def _create_legacy_database(path, histories=None):
    histories = histories or [
        [{"role": "user", "content": "Legacy conversation"}]
    ]

    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
            CREATE TABLE conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL DEFAULT 'New Conversation',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE conversation_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                history_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id)
                    ON DELETE CASCADE
            );
            INSERT INTO tasks (id, title) VALUES (41, 'Preserved task');
            INSERT INTO conversations (id, title)
            VALUES (7, 'Preserved conversation');
            """
        )

        for index, history in enumerate(histories):
            connection.execute(
                """
                INSERT INTO conversation_messages
                    (conversation_id, history_json, updated_at)
                VALUES (7, ?, ?)
                """,
                (json.dumps(history), f"2025-01-0{index + 1} 12:00:00"),
            )


def test_create_conversation(repository):
    conversation_id = repository.create_conversation()

    assert conversation_id > 0


def test_save_and_load_history(repository):
    conversation_id = repository.create_conversation()

    history = [
        {"role": "system", "content": "You are PAA."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hello!"},
    ]

    repository.save_history(conversation_id, history)

    saved_history = repository.get_history(conversation_id)

    assert saved_history == history


def test_list_conversations(repository):
    repository.create_conversation("Conversation One")
    repository.create_conversation("Conversation Two")

    conversations = repository.list_conversations()

    assert len(conversations) == 2


def test_delete_conversation(repository):
    conversation_id = repository.create_conversation()

    assert repository.delete_conversation(conversation_id) is True
    assert repository.delete_conversation(conversation_id) is False

    assert repository.get_history(conversation_id) is None


def test_save_invalid_history(repository):
    conversation_id = repository.create_conversation()

    with pytest.raises(ConversationRepositoryError, match="History must"):
        repository.save_history(conversation_id, "invalid")


@pytest.mark.parametrize(
    "history, message",
    [
        ([None], "message 0 must be an object"),
        ([{"content": "missing role"}], "must have a non-empty role"),
        ([{"role": "user"}], "must have text or null content"),
        ([{"role": "user", "content": []}], "must have text or null content"),
    ],
)
def test_save_rejects_invalid_message_structures(repository, history, message):
    conversation_id = repository.create_conversation()

    with pytest.raises(ConversationRepositoryError, match=message):
        repository.save_history(conversation_id, history)

    assert repository.get_history(conversation_id) == []


@pytest.mark.parametrize(
    "stored_history, message",
    [
        ("not json", "malformed JSON"),
        ("{}", "History must be a list"),
        ("[null]", "message 0 must be an object"),
        ('[{"content":"missing role"}]', "must have a non-empty role"),
        ('[{"role":"user"}]', "must have text or null content"),
    ],
)
def test_get_history_rejects_malformed_or_invalid_storage(
    repository,
    stored_history,
    message,
):
    conversation_id = repository.create_conversation()

    with db.get_connection() as connection:
        with connection:
            connection.execute(
                """
                UPDATE conversation_messages
                SET history_json = ?
                WHERE conversation_id = ?
                """,
                (stored_history, conversation_id),
            )

    with pytest.raises(ConversationRepositoryError, match=message):
        repository.get_history(conversation_id)


def test_initialization_enforces_one_message_row_per_conversation(repository):
    conversation_id = repository.create_conversation()

    with db.get_connection() as connection:
        indexes = connection.execute(
            "PRAGMA index_list(conversation_messages)"
        ).fetchall()
        assert any(
            index["unique"]
            and [
                column["name"]
                for column in connection.execute(
                    f'PRAGMA index_info("{index["name"]}")'
                ).fetchall()
            ]
            == ["conversation_id"]
            for index in indexes
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO conversation_messages
                    (conversation_id, history_json)
                VALUES (?, '[]')
                """,
                (conversation_id,),
            )


def test_legacy_migration_backs_up_without_losing_existing_data(
    tmp_path,
    monkeypatch,
):
    legacy_source = tmp_path / "legacy_source.sqlite3"
    migration_copy = tmp_path / "migration_copy.db"
    _create_legacy_database(legacy_source)
    shutil.copy2(legacy_source, migration_copy)

    existing_backup = (
        tmp_path / "migration_copy.db.pre-migration-existing.sqlite3"
    )
    existing_backup.write_bytes(b"keep this backup")
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", migration_copy)

    repository = ConversationRepository()

    backup_paths = list(
        tmp_path.glob("migration_copy.db.pre-migration-*.sqlite3")
    )
    backup_paths = [path for path in backup_paths if path != existing_backup]
    assert len(backup_paths) == 1
    assert existing_backup.read_bytes() == b"keep this backup"

    with sqlite3.connect(migration_copy) as migrated:
        assert migrated.execute(
            "PRAGMA journal_mode"
        ).fetchone()[0].lower() == "wal"
        assert migrated.execute("SELECT id, title FROM tasks").fetchall() == [
            (41, "Preserved task")
        ]
        assert migrated.execute(
            "SELECT id, title FROM conversations"
        ).fetchall() == [(7, "Preserved conversation")]
        assert migrated.execute(
            "SELECT COUNT(*) FROM conversation_messages"
        ).fetchone()[0] == 1
        assert migrated.execute(
            "SELECT COUNT(*) FROM pragma_index_list("
            "'conversation_messages') WHERE \"unique\" = 1"
        ).fetchone()[0] == 1

    with sqlite3.connect(backup_paths[0]) as backup:
        assert backup.execute("SELECT id, title FROM tasks").fetchall() == [
            (41, "Preserved task")
        ]
        assert backup.execute(
            "SELECT id, title FROM conversations"
        ).fetchall() == [(7, "Preserved conversation")]
        assert backup.execute(
            "SELECT COUNT(*) FROM conversation_messages"
        ).fetchone()[0] == 1
        assert backup.execute(
            "SELECT COUNT(*) FROM pragma_index_list("
            "'conversation_messages') WHERE \"unique\" = 1"
        ).fetchone()[0] == 0

    assert repository.get_history(7) == [
        {"role": "user", "content": "Legacy conversation"}
    ]


def test_migration_deduplicates_only_identical_histories(tmp_path, monkeypatch):
    history = [
        {"role": "user", "content": "Same history"},
        {"role": "assistant", "content": "Same response"},
    ]
    path = tmp_path / "duplicate_legacy.db"
    _create_legacy_database(path, histories=[history, history])
    formatted_history = json.dumps(history, indent=2)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE conversation_messages
            SET history_json = ?
            WHERE id = 2
            """,
            (formatted_history,),
        )
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", path)

    ConversationRepository()

    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            """
            SELECT id, history_json
            FROM conversation_messages
            WHERE conversation_id = 7
            """
        ).fetchall()

    assert len(rows) == 1
    assert rows[0][0] == 2
    assert rows[0][1] == formatted_history
    assert json.loads(rows[0][1]) == history


def test_migration_preserves_conflicting_histories_and_raises(
    tmp_path,
    monkeypatch,
):
    histories = [
        [{"role": "user", "content": "First history"}],
        [{"role": "user", "content": "Different history"}],
    ]
    path = tmp_path / "conflicting_legacy.db"
    _create_legacy_database(path, histories=[histories[0], histories[0]])
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute(
            """
            INSERT INTO conversations (id, title)
            VALUES (8, 'Conflicting conversation')
            """
        )
        connection.executemany(
            """
            INSERT INTO conversation_messages
                (conversation_id, history_json)
            VALUES (8, ?)
            """,
            [(json.dumps(history),) for history in histories],
        )
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", path)

    with pytest.raises(
        ConversationMigrationError,
        match=r"conversation 8: it has 2 conflicting message histories",
    ):
        ConversationRepository()

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "PRAGMA journal_mode"
        ).fetchone()[0].lower() == "delete"
        assert connection.execute(
            "SELECT id, title FROM tasks"
        ).fetchall() == [(41, "Preserved task")]
        assert connection.execute(
            "SELECT id, title FROM conversations ORDER BY id"
        ).fetchall() == [
            (7, "Preserved conversation"),
            (8, "Conflicting conversation"),
        ]
        assert connection.execute(
            """
            SELECT id, conversation_id, history_json
            FROM conversation_messages
            ORDER BY id
            """
        ).fetchall() == [
            (1, 7, json.dumps(histories[0])),
            (2, 7, json.dumps(histories[0])),
            (3, 8, json.dumps(histories[0])),
            (4, 8, json.dumps(histories[1])),
        ]
        assert connection.execute(
            "SELECT COUNT(*) FROM pragma_index_list("
            "'conversation_messages') WHERE \"unique\" = 1"
        ).fetchone()[0] == 0

    backup_paths = list(
        tmp_path.glob("conflicting_legacy.db.pre-migration-*.sqlite3")
    )
    assert len(backup_paths) == 1
    with sqlite3.connect(backup_paths[0]) as backup:
        assert backup.execute(
            "SELECT COUNT(*) FROM conversation_messages"
        ).fetchone()[0] == 4


@pytest.mark.parametrize(
    "stored_history, message",
    [
        ("not json", "malformed JSON"),
        ('[{"role":"user"}]', "is invalid: History message 0"),
    ],
)
def test_migration_rejects_malformed_duplicate_histories(
    tmp_path,
    monkeypatch,
    stored_history,
    message,
):
    path = tmp_path / "invalid_duplicate_legacy.db"
    _create_legacy_database(path, histories=[[]])
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE conversation_messages
            SET history_json = ?
            WHERE id = 1
            """,
            (stored_history,),
        )
        connection.execute(
            """
            INSERT INTO conversation_messages
                (conversation_id, history_json)
            VALUES (7, ?)
            """,
            (stored_history,),
        )
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", path)

    with pytest.raises(ConversationRepositoryError, match=message):
        ConversationRepository()

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            """
            SELECT history_json
            FROM conversation_messages
            WHERE conversation_id = 7
            ORDER BY id
            """
        ).fetchall() == [(stored_history,), (stored_history,)]
        assert connection.execute(
            "SELECT COUNT(*) FROM pragma_index_list("
            "'conversation_messages') WHERE \"unique\" = 1"
        ).fetchone()[0] == 0


def test_database_backup_restores_task_and_conversation_data(tmp_path):
    source_path = tmp_path / "backup_source.db"
    restored_path = tmp_path / "restored.db"
    existing_backup = (
        tmp_path / "backup_source.db.pre-migration-existing.sqlite3"
    )
    existing_backup.write_bytes(b"do not overwrite")
    history = [
        {"role": "user", "content": "Remember this conversation"},
        {"role": "assistant", "content": "I will."},
    ]
    _create_legacy_database(source_path, histories=[history])

    with sqlite3.connect(source_path) as source:
        source.execute("PRAGMA journal_mode = WAL")
        backup_path = db._backup_database(source, source_path)

    with sqlite3.connect(backup_path) as backup:
        with sqlite3.connect(restored_path) as restored:
            backup.backup(restored)

    with sqlite3.connect(restored_path) as restored:
        assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert restored.execute(
            "SELECT id, title FROM tasks"
        ).fetchall() == [(41, "Preserved task")]
        assert restored.execute(
            "SELECT id, title FROM conversations"
        ).fetchall() == [(7, "Preserved conversation")]
        restored_history = restored.execute(
            """
            SELECT history_json
            FROM conversation_messages
            WHERE conversation_id = 7
            """
        ).fetchone()[0]
        assert json.loads(restored_history) == history

    assert existing_backup.read_bytes() == b"do not overwrite"
    with sqlite3.connect(source_path) as source:
        assert source.execute(
            "SELECT id, title FROM tasks"
        ).fetchall() == [(41, "Preserved task")]
        assert source.execute(
            "SELECT history_json FROM conversation_messages"
        ).fetchone()[0] == json.dumps(history)
