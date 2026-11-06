
import pytest

from app.database.conversation_repository import ConversationRepository


@pytest.fixture
def repository(tmp_path, monkeypatch):
    from app.database import conversation_repository as module

    db_path = tmp_path / "test_conversations.db"

    # Use an isolated database for each test.
    from app.database import db

    original_connection = db.get_connection

    def test_connection():
        return original_connection(db_path)

    monkeypatch.setattr(module, "get_connection", test_connection)

    return ConversationRepository()


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

    with pytest.raises(ValueError):
        repository.save_history(conversation_id, "invalid")
