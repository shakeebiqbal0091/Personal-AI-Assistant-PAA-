
from unittest.mock import MagicMock

import pytest

from app.core.intent_router import IntentRouter
from app.database.memory_repository import (
    MAX_RETRIEVED_MEMORIES,
    MemoryRepository,
)


def test_validate_create_task():

    intent = IntentRouter.validate(
        "create_task",
        {
            "title": "Learn Python",
            "description": "",
        },
    )

    assert intent.name == "create_task"
    assert intent.arguments["title"] == "Learn Python"


def test_validate_list_tasks():

    intent = IntentRouter.validate(
        "list_tasks",
        {"status": "pending"},
    )

    assert intent.arguments["status"] == "pending"


def test_validate_complete_task():

    intent = IntentRouter.validate(
        "complete_task",
        {"task_id": 10},
    )

    assert intent.arguments["task_id"] == 10


def test_validate_delete_task():

    intent = IntentRouter.validate(
        "delete_task",
        {"task_id": 5},
    )

    assert intent.arguments["task_id"] == 5


def test_validate_search_memories_normalizes_query():
    intent = IntentRouter.validate(
        "search_memories",
        {"query": "  saved Python notes  "},
    )

    assert intent.arguments == {"query": "saved Python notes"}


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"query": 123},
        {"query": "Python", "limit": 100},
    ],
)
def test_validate_search_memories_rejects_malformed_arguments(arguments):
    with pytest.raises(ValueError):
        IntentRouter.validate("search_memories", arguments)


def test_validate_propose_memory_preserves_exact_content_and_category():
    intent = IntentRouter.validate(
        "propose_memory",
        {
            "content": " Prefers concise answers ",
            "category": "preference",
        },
    )

    assert intent.arguments == {
        "content": "Prefers concise answers",
        "category": "preference",
    }


@pytest.mark.parametrize(
    "arguments",
    [
        {"content": " ", "category": None},
        {"content": "Remember this", "category": "invalid"},
        {"content": 123, "category": None},
        {"content": "Remember this", "category": "project", "extra": True},
    ],
)
def test_validate_propose_memory_rejects_invalid_arguments(arguments):
    with pytest.raises(ValueError):
        IntentRouter.validate("propose_memory", arguments)


def test_reject_unknown_intent():

    with pytest.raises(ValueError):
        IntentRouter.validate("send_email", {})


def test_reject_empty_task_title():

    with pytest.raises(ValueError):
        IntentRouter.validate(
            "create_task",
            {
                "title": " ",
                "description": "",
            },
        )


def test_reject_invalid_task_id():

    with pytest.raises(ValueError):
        IntentRouter.validate(
            "complete_task",
            {"task_id": -1},
        )


def test_reject_boolean_task_id():

    with pytest.raises(ValueError):
        IntentRouter.validate(
            "delete_task",
            {"task_id": True},
        )


def test_reject_invalid_task_status():

    with pytest.raises(ValueError):
        IntentRouter.validate(
            "list_tasks",
            {"status": "archived"},
        )


def test_reject_extra_arguments():

    with pytest.raises(ValueError):
        IntentRouter.validate(
            "delete_task",
            {
                "task_id": 5,
                "extra": "unexpected",
            },
        )


def test_route_create_task():

    manager = MagicMock()
    manager.create_task.return_value = 15

    result = IntentRouter.route(
        "create_task",
        {
            "title": "Learn Python",
            "description": "",
        },
        manager,
    )

    assert result["success"] is True
    assert result["task_id"] == 15

    manager.create_task.assert_called_once_with(
        "Learn Python",
        "",
    )


def test_route_delete_task_requests_confirmation_without_deleting():
    manager = MagicMock()
    manager.list_tasks.return_value = [
        {
            "id": 5,
            "title": "Temporary task",
            "description": "Review before removal",
            "status": "pending",
        }
    ]

    result = IntentRouter.route(
        "delete_task",
        {"task_id": 5},
        manager,
    )

    assert result["pending_confirmation"] is True
    assert result["deleted"] is False
    assert result["task"] == manager.list_tasks.return_value[0]
    manager.delete_task.assert_not_called()


def test_route_delete_task_missing_returns_no_pending_request():
    manager = MagicMock()
    manager.list_tasks.return_value = []

    result = IntentRouter.route(
        "delete_task",
        {"task_id": 5},
        manager,
    )

    assert result["success"] is False
    assert "not found" in result["message"]
    assert "pending_confirmation" not in result
    manager.delete_task.assert_not_called()


def test_route_search_memories_returns_bounded_repository_records():
    repository = MemoryRepository()
    matching_id = repository.create_memory(
        "The project uses Python for data processing.",
        "project",
    )
    repository.create_memory("I prefer quiet mornings.", "preference")
    expected = repository.get_memory(matching_id)

    result = IntentRouter.route(
        "search_memories",
        {"query": "project Python"},
        MagicMock(),
        memory_repository=repository,
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["memories"] == [
        {
            "id": matching_id,
            "content": expected["content"],
            "category": expected["category"],
            "created_at": expected["created_at"],
            "updated_at": expected["updated_at"],
        }
    ]


def test_route_search_memories_handles_empty_and_no_match_queries():
    repository = MemoryRepository()
    repository.create_memory("Project uses Python.", "project")

    empty_result = IntentRouter.route(
        "search_memories",
        {"query": "  "},
        MagicMock(),
        memory_repository=repository,
    )
    no_match_result = IntentRouter.route(
        "search_memories",
        {"query": "unrelated gardening topic"},
        MagicMock(),
        memory_repository=repository,
    )

    assert empty_result["success"] is True
    assert empty_result["memories"] == []
    assert empty_result["count"] == 0
    assert "No matching saved memory records" in empty_result["message"]
    assert no_match_result["memories"] == []


def test_route_search_memories_preserves_repository_limit_and_order():
    repository = MemoryRepository()
    expected_ids = [
        repository.create_memory(f"Python project note {index}")
        for index in range(MAX_RETRIEVED_MEMORIES + 2)
    ]

    first = IntentRouter.route(
        "search_memories",
        {"query": "Python project"},
        MagicMock(),
        memory_repository=repository,
    )
    second = IntentRouter.route(
        "search_memories",
        {"query": "Python project"},
        MagicMock(),
        memory_repository=repository,
    )

    assert first["count"] == MAX_RETRIEVED_MEMORIES
    assert [memory["id"] for memory in first["memories"]] == expected_ids[
        :MAX_RETRIEVED_MEMORIES
    ]
    assert second["memories"] == first["memories"]


def test_route_propose_memory_never_writes_to_repository():
    repository = MagicMock()

    result = IntentRouter.route(
        "propose_memory",
        {
            "content": "Prefers concise answers",
            "category": "preference",
        },
        MagicMock(),
        memory_repository=repository,
    )

    assert result == {
        "success": True,
        "intent": "propose_memory",
        "pending_confirmation": True,
        "proposal": {
            "content": "Prefers concise answers",
            "category": "preference",
        },
        "message": (
            "This memory proposal has not been saved. It requires "
            "explicit confirmation in Streamlit."
        ),
    }
    repository.create_memory.assert_not_called()
    repository.update_memory.assert_not_called()
    repository.delete_memory.assert_not_called()


def test_invalid_request_never_calls_task_manager():

    manager = MagicMock()

    with pytest.raises(ValueError):
        IntentRouter.route(
            "delete_task",
            {"task_id": 0},
            manager,
        )

    manager.delete_task.assert_not_called()



def test_task_manager_failure_is_handled():

    manager = MagicMock()

    manager.create_task.side_effect = RuntimeError(
        "Database unavailable"
    )

    with pytest.raises(RuntimeError):
        IntentRouter.route(
            "create_task",
            {
                "title": "Learn Python",
                "description": "",
            },
            manager,
        )


def test_invalid_arguments_do_not_modify_database():

    manager = MagicMock()

    result = None

    try:
        result = IntentRouter.route(
            "create_task",
            {
                "title": "",
                "description": "",
            },
            manager,
        )
    except ValueError:
        pass

    assert result is None
    manager.create_task.assert_not_called()
