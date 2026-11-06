
from unittest.mock import MagicMock

import pytest

import app.core.agent as agent_module
from app.core.agent import PersonalAssistant
from app.core.config import Settings
from types import SimpleNamespace


@pytest.fixture
def setup_agent(monkeypatch):
    settings = Settings(
        app_name="Personal AI Assistant",
        api_key="test-key",
        base_url="https://example.com",
        model="test-model",
        debug=False,
    )

    monkeypatch.setattr(
        agent_module,
        "get_settings",
        lambda: settings
    )

    client = MagicMock()
    task_manager = MagicMock()

    assistant = PersonalAssistant(
        client=client,
        task_manager=task_manager,
    )

    return assistant, client, task_manager


def test_create_task_tool(setup_agent):
    assistant, client, manager = setup_agent

    manager.create_task.return_value = 5

    result = assistant._execute_tool(
        "create_task",
        {
            "title": "Learn Python",
            "description": "Practice Python",
        }
    )

    assert result["success"] is True
    assert result["task_id"] == 5
    manager.create_task.assert_called_once()


def test_list_tasks_tool(setup_agent):
    assistant, client, manager = setup_agent

    manager.list_tasks.return_value = [
        {"id": 1, "title": "Learn Python"}
    ]

    result = assistant._execute_tool(
        "list_tasks",
        {"status": "pending"}
    )

    assert result["count"] == 1
    manager.list_tasks.assert_called_once_with("pending")


def test_complete_task_tool(setup_agent):
    assistant, client, manager = setup_agent

    manager.complete_task.return_value = True

    result = assistant._execute_tool(
        "complete_task",
        {"task_id": 1}
    )

    assert result["success"] is True
    manager.complete_task.assert_called_once_with(1)


def test_delete_task_tool(setup_agent):
    assistant, client, manager = setup_agent

    manager.delete_task.return_value = True

    result = assistant._execute_tool(
        "delete_task",
        {"task_id": 1}
    )

    assert result["success"] is True
    manager.delete_task.assert_called_once_with(1)


def test_unknown_tool(setup_agent):
    assistant, client, manager = setup_agent

    result = assistant._execute_tool(
        "unknown_tool",
        {}
    )

    assert result["success"] is False
    manager.create_task.assert_not_called()


def test_chat_executes_ai_tool_call(setup_agent):
    assistant, client, manager = setup_agent

    manager.create_task.return_value = 10

    tool_call = SimpleNamespace(
        id="call_123",
        function=SimpleNamespace(
            name="create_task",
            arguments='{"title":"Learn Python","description":""}'
        ),
        model_dump=lambda: {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "create_task",
                "arguments": '{"title":"Learn Python","description":""}'
            }
        }
    )

    first_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=None,
                    tool_calls=[tool_call]
                )
            )
        ]
    )

    second_response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="Your task has been created successfully.",
                    tool_calls=None
                )
            )
        ]
    )

    client.chat.completions.create.side_effect = [
        first_response,
        second_response,
    ]

    result = assistant.chat("Create a task to learn Python.")

    assert "created successfully" in result
    manager.create_task.assert_called_once_with(
        "Learn Python",
        ""
    )
    assert len(client.chat.completions.create.call_args_list) == 2
