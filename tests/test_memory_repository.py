import pytest

from app.database import db
from app.database.conversation_repository import ConversationRepository
from app.database.memory_repository import (
    MAX_MEMORY_CONTENT_LENGTH,
    DuplicateMemoryError,
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryRepository,
    MemoryRepositoryError,
)
from app.tools.task_manager import TaskManager


@pytest.fixture
def repository(tmp_path, monkeypatch):
    db_path = tmp_path / "test_memories.db"
    monkeypatch.setattr(db, "DEFAULT_DB_PATH", db_path)
    return MemoryRepository(db_path=db_path)


def test_create_memory(repository):
    memory_id = repository.create_memory(
        "  Prefers email updates.  ",
        " Preference ",
    )

    memory = repository.get_memory(memory_id)
    assert memory["id"] == memory_id
    assert memory["content"] == "Prefers email updates."
    assert memory["category"] == "preference"
    assert memory["created_at"]
    assert memory["updated_at"]


def test_create_memory_with_status_distinguishes_new_and_duplicate(repository):
    first_id, created = repository.create_memory_with_status(
        "Prefers concise answers",
        "preference",
    )
    duplicate_id, duplicate_created = repository.create_memory_with_status(
        "  PREFERS concise answers ",
        "project",
    )

    assert created is True
    assert duplicate_created is False
    assert duplicate_id == first_id
    assert repository.get_memory(first_id)["category"] == "preference"
    assert len(repository.list_memories()) == 1


def test_list_memories(repository):
    first_id = repository.create_memory("First memory")
    second_id = repository.create_memory("Second memory", "fact")

    memories = repository.list_memories()

    assert [memory["id"] for memory in memories] == [first_id, second_id]
    assert [memory["content"] for memory in memories] == [
        "First memory",
        "Second memory",
    ]


def test_get_memory_returns_none_for_missing_id(repository):
    assert repository.get_memory(999) is None


def test_update_memory_content(repository):
    memory_id = repository.create_memory("Old content")
    created_at = repository.get_memory(memory_id)["updated_at"]

    updated = repository.update_memory(
        memory_id,
        content="New content",
    )

    assert updated["content"] == "New content"
    assert updated["updated_at"] != created_at


def test_conditional_update_succeeds_for_expected_version(repository):
    memory_id = repository.create_memory("Old content")
    current = repository.get_memory(memory_id)

    updated = repository.update_memory(
        memory_id,
        content="New content",
        expected_updated_at=current["updated_at"],
    )

    assert updated["content"] == "New content"
    assert updated["updated_at"] != current["updated_at"]


def test_conditional_update_rejects_stale_version(repository):
    memory_id = repository.create_memory("Old content")
    stale_version = repository.get_memory(memory_id)["updated_at"]
    repository.update_memory(memory_id, content="Newer content")

    with pytest.raises(MemoryConflictError, match="changed since it was loaded"):
        repository.update_memory(
            memory_id,
            content="Stale overwrite",
            expected_updated_at=stale_version,
        )

    assert repository.get_memory(memory_id)["content"] == "Newer content"


def test_conditional_update_reports_missing_memory(repository):
    with pytest.raises(MemoryNotFoundError, match="Memory 999 was not found"):
        repository.update_memory(
            999,
            content="New content",
            expected_updated_at="2026-01-01 00:00:00",
        )


def test_conditional_update_preserves_duplicate_conflict(repository):
    repository.create_memory("Existing content")
    memory_id = repository.create_memory("Original content")
    version = repository.get_memory(memory_id)["updated_at"]

    with pytest.raises(DuplicateMemoryError, match="identical content"):
        repository.update_memory(
            memory_id,
            content="Existing content",
            expected_updated_at=version,
        )

    assert repository.get_memory(memory_id)["content"] == "Original content"


def test_update_memory_category(repository):
    memory_id = repository.create_memory("A useful fact")
    previous_updated_at = repository.get_memory(memory_id)["updated_at"]

    updated = repository.update_memory(
        memory_id,
        category=" PROJECT ",
    )

    assert updated["category"] == "project"
    assert updated["updated_at"] != previous_updated_at


def test_update_memory_does_not_change_timestamp_for_noop(repository):
    memory_id = repository.create_memory("Unchanged")
    before = repository.get_memory(memory_id)["updated_at"]

    updated = repository.update_memory(memory_id, content="Unchanged")

    assert updated["updated_at"] == before


def test_update_memory_requires_at_least_one_field(repository):
    memory_id = repository.create_memory("Memory")

    with pytest.raises(MemoryRepositoryError, match="At least one"):
        repository.update_memory(memory_id)


def test_update_memory_raises_for_missing_id(repository):
    with pytest.raises(MemoryNotFoundError, match="Memory 999 was not found"):
        repository.update_memory(999, content="Updated")


def test_delete_memory(repository):
    memory_id = repository.create_memory("Remove me")

    assert repository.delete_memory(memory_id) is True
    assert repository.get_memory(memory_id) is None
    assert repository.list_memories() == []


def test_conditional_delete_succeeds_for_matching_snapshot(repository):
    memory_id = repository.create_memory("Remove me", "fact")
    snapshot = repository.get_memory(memory_id)

    assert repository.delete_memory_if_unchanged(
        memory_id,
        expected_content=snapshot["content"],
        expected_category=snapshot["category"],
        expected_updated_at=snapshot["updated_at"],
    ) is True
    assert repository.get_memory(memory_id) is None


def test_conditional_delete_rejects_stale_snapshot(repository):
    memory_id = repository.create_memory("Original content", "fact")
    snapshot = repository.get_memory(memory_id)
    repository.update_memory(
        memory_id,
        content="Updated content",
        category="project",
    )

    with pytest.raises(MemoryConflictError, match="changed since deletion"):
        repository.delete_memory_if_unchanged(
            memory_id,
            expected_content=snapshot["content"],
            expected_category=snapshot["category"],
            expected_updated_at=snapshot["updated_at"],
        )

    assert repository.get_memory(memory_id)["content"] == "Updated content"
    assert repository.get_memory(memory_id)["category"] == "project"


def test_conditional_delete_reports_missing_memory(repository):
    with pytest.raises(MemoryNotFoundError, match="Memory 999 was not found"):
        repository.delete_memory_if_unchanged(
            999,
            expected_content="Missing",
            expected_category=None,
            expected_updated_at="2026-01-01 00:00:00",
        )


def test_delete_nonexistent_memory(repository):
    assert repository.delete_memory(999) is False


@pytest.mark.parametrize("content", ["", "   ", "\n\t "])
def test_rejects_blank_content(repository, content):
    with pytest.raises(MemoryRepositoryError, match="cannot be empty"):
        repository.create_memory(content)


def test_rejects_oversized_content(repository):
    with pytest.raises(MemoryRepositoryError, match="cannot exceed"):
        repository.create_memory("x" * (MAX_MEMORY_CONTENT_LENGTH + 1))


@pytest.mark.parametrize("category", ["unknown", "user preference", 7])
def test_rejects_invalid_category(repository, category):
    with pytest.raises(MemoryRepositoryError, match="category"):
        repository.create_memory("Memory", category)


def test_duplicate_creation_returns_existing_id_without_overwriting(
    repository,
):
    original_id = repository.create_memory(
        "  Prefers   tea ",
        "preference",
    )

    duplicate_id = repository.create_memory(
        "prefers tea",
        "fact",
    )

    assert duplicate_id == original_id
    assert repository.list_memories() == [
        {
            **repository.get_memory(original_id),
            "content": "Prefers   tea",
            "category": "preference",
        }
    ]


def test_update_rejects_duplicate_content(repository):
    repository.create_memory("Same fact")
    second_id = repository.create_memory("Different fact")

    with pytest.raises(DuplicateMemoryError, match="identical content"):
        repository.update_memory(second_id, content=" same fact ")

    assert repository.get_memory(second_id)["content"] == "Different fact"


def test_memory_persists_across_repository_instances(repository):
    memory_id = repository.create_memory("Persistent memory", "routine")

    reopened = MemoryRepository(db_path=repository.db_path)

    assert reopened.get_memory(memory_id)["content"] == "Persistent memory"
    assert reopened.get_memory(memory_id)["category"] == "routine"


def test_memory_operations_preserve_task_and_conversation_records(
    repository,
):
    task_manager = TaskManager(db_path=repository.db_path)
    conversation_repository = ConversationRepository()
    task_id = task_manager.create_task("Keep this task")
    conversation_id = conversation_repository.create_conversation(
        "Keep this conversation",
    )
    history = [{"role": "user", "content": "Keep this history"}]
    conversation_repository.save_history(conversation_id, history)

    repository.create_memory("Separate memory")
    repository.update_memory(
        repository.list_memories()[0]["id"],
        category="fact",
    )

    assert task_manager.list_tasks()[0]["id"] == task_id
    assert conversation_repository.list_conversations()[0]["id"] == (
        conversation_id
    )
    assert conversation_repository.get_history(conversation_id) == history

    with db.get_connection(repository.db_path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == (
            "ok"
        )


def test_memory_content_is_stored_as_parameterized_data(repository):
    content = "'; DROP TABLE memories; --"

    memory_id = repository.create_memory(content)

    assert repository.get_memory(memory_id)["content"] == content
    assert len(repository.list_memories()) == 1


def test_memory_id_validation_rejects_invalid_values(repository):
    for memory_id in (0, -1, True, "1"):
        with pytest.raises(MemoryRepositoryError, match="positive integer"):
            repository.get_memory(memory_id)
