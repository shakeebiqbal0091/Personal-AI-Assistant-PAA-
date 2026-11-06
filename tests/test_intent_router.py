
from unittest.mock import MagicMock

import pytest

from app.core.intent_router import IntentRouter


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
