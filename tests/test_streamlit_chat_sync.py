import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import app.core.agent as agent_module
import app.database.conversation_repository as conversation_repository_module
import app.tools.task_manager as task_manager_module


class FakeConversationRepository:
    conversations = []
    histories = {}

    def __init__(self):
        pass

    def list_conversations(self):
        return list(self.conversations)

    def delete_conversation(self, conversation_id):
        self.conversations = [
            item
            for item in self.conversations
            if item["id"] != conversation_id
        ]
        return True


class FakeTaskManager:
    tasks = {}
    deleted_ids = []

    def list_tasks(self, status="all"):
        tasks = list(self.tasks.values())
        if status == "all":
            return tasks
        return [task for task in tasks if task["status"] == status]

    def create_task(self, title, description=""):
        return 1

    def delete_task(self, task_id):
        self.deleted_ids.append(task_id)
        return self.tasks.pop(task_id, None) is not None

    def delete_task_if_unchanged(
        self, task_id, title, description, status
    ):
        task = self.tasks.get(task_id)
        if task is None or any(
            task.get(field) != expected
            for field, expected in (
                ("title", title),
                ("description", description),
                ("status", status),
            )
        ):
            return False

        self.deleted_ids.append(task_id)
        del self.tasks[task_id]
        return True


class FakeAssistant:
    mode = "success"
    default_conversation_id = None
    delete_task_id = 4

    def __init__(
        self,
        conversation_id=None,
        conversation_repository=None,
    ):
        self.conversation_repository = conversation_repository
        self.conversation_id = (
            conversation_id
            if conversation_id is not None
            else self.default_conversation_id
        )
        self.conversation_history = [
            {"role": "system", "content": "system prompt"}
        ]
        if self.conversation_id is not None:
            self.conversation_history.extend(
                self.conversation_repository.histories.get(
                    self.conversation_id,
                    [],
                )
            )

    def chat(self, prompt):
        if self.mode == "fail_before_checkpoint":
            raise RuntimeError("request failed before checkpoint")

        self.conversation_history.append(
            {"role": "user", "content": prompt}
        )

        if self.mode == "delete_request":
            task = dict(
                FakeTaskManager.tasks.get(
                    self.delete_task_id,
                    {
                        "id": self.delete_task_id,
                        "title": "Missing task",
                        "description": "",
                        "status": "pending",
                    },
                )
            )
            result = {
                "success": True,
                "intent": "delete_task",
                "pending_confirmation": True,
                "deleted": False,
                "task": task,
                "message": (
                    "The task has not been deleted. It is awaiting "
                    "confirmation."
                ),
            }
            self.conversation_history.extend(
                [
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_delete",
                                "type": "function",
                                "function": {
                                    "name": "delete_task",
                                    "arguments": (
                                        f'{{"task_id":{self.delete_task_id}}}'
                                    ),
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call_delete",
                        "content": json.dumps(result),
                    },
                    {
                        "role": "assistant",
                        "content": (
                            "Please review and confirm the deletion. "
                            "No task has been deleted."
                        ),
                    },
                ]
            )
            if self.conversation_id is None:
                self.conversation_id = 1
                self.conversation_repository.conversations.append(
                    {"id": 1, "title": prompt}
                )
            return "Please review and confirm the deletion."

        if self.mode == "fail_after_checkpoint":
            if self.conversation_id is None:
                self.conversation_id = 1
            self.conversation_history.extend(
                [
                    {
                        "role": "assistant",
                        "content": "hidden tool-call text",
                        "tool_calls": [{"id": "call_1"}],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": "call_1",
                        "content": "hidden tool result",
                    },
                ]
            )
            raise RuntimeError("follow-up request failed")

        self.conversation_history.append(
            {"role": "assistant", "content": "assistant reply"}
        )
        if self.conversation_id is None:
            self.conversation_id = 1
            self.conversation_repository.conversations.append(
                {"id": 1, "title": prompt}
            )
        return "assistant reply"

    def reset_conversation(self):
        self.conversation_history = [
            {"role": "system", "content": "system prompt"}
        ]


def _run_app(monkeypatch):
    monkeypatch.setattr(
        agent_module,
        "PersonalAssistant",
        FakeAssistant,
    )
    monkeypatch.setattr(
        conversation_repository_module,
        "ConversationRepository",
        FakeConversationRepository,
    )
    monkeypatch.setattr(
        task_manager_module,
        "TaskManager",
        FakeTaskManager,
    )

    return AppTest.from_file(
        str(Path(__file__).parents[1] / "app" / "main.py")
    ).run()


def _rendered_bubbles(app):
    return [
        markdown.value
        for chat_message in app.chat_message
        for markdown in chat_message.markdown
    ]


def _reset_fakes():
    FakeConversationRepository.conversations = []
    FakeConversationRepository.histories = {}
    FakeAssistant.mode = "success"
    FakeAssistant.default_conversation_id = None
    FakeAssistant.delete_task_id = 4
    FakeTaskManager.tasks = {
        4: {
            "id": 4,
            "title": "Target task",
            "description": "Exact requested task",
            "status": "pending",
        },
        9: {
            "id": 9,
            "title": "Other task",
            "description": "Must remain",
            "status": "pending",
        },
    }
    FakeTaskManager.deleted_ids = []


def test_successful_chat_displays_history_user_and_assistant(monkeypatch):
    _reset_fakes()

    app = _run_app(monkeypatch)
    app.chat_input[0].set_value("Hello").run()

    assert _rendered_bubbles(app) == ["Hello", "assistant reply"]
    assert not app.error


def test_failure_before_checkpoint_hides_unsaved_user_message(monkeypatch):
    _reset_fakes()
    FakeAssistant.mode = "fail_before_checkpoint"

    app = _run_app(monkeypatch)
    app.chat_input[0].set_value("Do not display me").run()

    assert _rendered_bubbles(app) == []
    assert any(
        "request failed before checkpoint" in error.value
        for error in app.error
    )


def test_failure_after_checkpoint_displays_only_user_bubble(monkeypatch):
    _reset_fakes()
    FakeAssistant.mode = "fail_after_checkpoint"

    app = _run_app(monkeypatch)
    app.chat_input[0].set_value("Create a task").run()

    assert _rendered_bubbles(app) == ["Create a task"]
    assert any(
        "follow-up request failed" in error.value
        for error in app.error
    )


def test_switching_conversations_replaces_displayed_history(monkeypatch):
    _reset_fakes()
    FakeConversationRepository.conversations = [
        {"id": 1, "title": "Alpha"},
        {"id": 2, "title": "Beta"},
    ]
    FakeConversationRepository.histories = {
        1: [{"role": "user", "content": "Alpha conversation"}],
        2: [
            {"role": "user", "content": "Beta conversation"},
            {
                "role": "assistant",
                "content": "hidden tool-call text",
                "tool_calls": [{"id": "call_2"}],
            },
            {
                "role": "tool",
                "tool_call_id": "call_2",
                "content": "hidden tool result",
            },
            {"role": "assistant", "content": "Beta reply"},
        ],
    }
    FakeAssistant.mode = "success"
    FakeAssistant.default_conversation_id = None

    app = _run_app(monkeypatch)
    app.selectbox(key="conversation_select_None").select("Alpha (#1)").run()
    assert _rendered_bubbles(app) == ["Alpha conversation"]

    app.selectbox(key="conversation_select_1").select("Beta (#2)").run()

    assert _rendered_bubbles(app) == ["Beta conversation", "Beta reply"]
    assert all("Alpha" not in bubble for bubble in _rendered_bubbles(app))


def _request_pending_delete(monkeypatch, other_conversation=False):
    _reset_fakes()
    FakeAssistant.mode = "delete_request"
    if other_conversation:
        FakeConversationRepository.conversations.append(
            {"id": 2, "title": "Other conversation"}
        )
    app = _run_app(monkeypatch)
    app.chat_input[0].set_value("Delete the target task").run()
    return app


def test_ai_delete_request_requires_confirmation_and_targets_exact_task(
    monkeypatch,
):
    app = _request_pending_delete(monkeypatch)

    assert FakeTaskManager.deleted_ids == []
    assert _rendered_bubbles(app) == [
        "Delete the target task",
        "Please review and confirm the deletion. No task has been deleted.",
    ]
    assert any("Target task" in warning.value for warning in app.warning)
    assert any(button.label == "Confirm Delete" for button in app.button)

    app.button(key="confirm_delete_call_delete").click().run()

    assert FakeTaskManager.deleted_ids == [4]
    assert 4 not in FakeTaskManager.tasks
    assert 9 in FakeTaskManager.tasks
    assert any("Task #4 deleted." in success.value for success in app.success)
    assert app.session_state.pending_task_deletions == []
    app.run()
    assert not any(button.label == "Confirm Delete" for button in app.button)


def test_duplicate_approvals_delete_task_at_most_once(monkeypatch):
    app = _request_pending_delete(monkeypatch)

    first = app.session_state.pending_task_deletions[0]
    app.session_state.pending_task_deletions.append(
        {
            "conversation_id": first["conversation_id"],
            "tool_call_id": "call_delete_duplicate",
            "task": dict(first["task"]),
        }
    )
    app.run()

    app.button(key="confirm_delete_call_delete").click().run()
    assert FakeTaskManager.deleted_ids == [4]

    app.run()
    assert app.session_state.pending_task_deletions == [
        {
            "conversation_id": first["conversation_id"],
            "tool_call_id": "call_delete_duplicate",
            "task": first["task"],
        }
    ]

    app.button(key="confirm_delete_call_delete_duplicate").click().run()

    assert FakeTaskManager.deleted_ids == [4]
    assert 4 not in FakeTaskManager.tasks
    assert app.session_state.pending_task_deletions == []


def test_cancel_pending_delete_leaves_task_intact(monkeypatch):
    app = _request_pending_delete(monkeypatch)

    app.button(key="cancel_delete_call_delete").click().run()

    assert FakeTaskManager.deleted_ids == []
    assert 4 in FakeTaskManager.tasks
    assert app.session_state.pending_task_deletions == []
    app.run()
    assert not any(button.label == "Confirm Delete" for button in app.button)


def test_switching_conversations_clears_pending_delete(monkeypatch):
    app = _request_pending_delete(monkeypatch, other_conversation=True)

    app.selectbox(key="conversation_select_1").select(
        "Other conversation (#2)"
    ).run()

    assert not any(button.label == "Confirm Delete" for button in app.button)
    assert FakeTaskManager.deleted_ids == []


@pytest.mark.parametrize(
    "control_label",
    ["➕ New Conversation", "Clear Current Conversation", "🗑️ Delete Current Conversation"],
)
def test_new_reset_and_delete_conversation_clear_pending_delete(
    monkeypatch,
    control_label,
):
    app = _request_pending_delete(monkeypatch)

    next(
        button for button in app.button if button.label == control_label
    ).click().run()

    assert not any(button.label == "Confirm Delete" for button in app.button)
    assert FakeTaskManager.deleted_ids == []


def test_missing_task_at_confirmation_shows_error_without_deleting(
    monkeypatch,
):
    app = _request_pending_delete(monkeypatch)
    FakeTaskManager.tasks.pop(4)

    app.button(key="confirm_delete_call_delete").click().run()

    assert FakeTaskManager.deleted_ids == []
    assert any(
        "Task #4 no longer exists" in error.value
        for error in app.error
    )
    assert app.session_state.pending_task_deletions == []
    app.run()
    assert not any(button.label == "Confirm Delete" for button in app.button)


def test_changed_task_cannot_be_deleted_by_stale_approval(monkeypatch):
    app = _request_pending_delete(monkeypatch)
    FakeTaskManager.tasks[4]["title"] = "Replaced task"

    app.button(key="confirm_delete_call_delete").click().run()

    assert FakeTaskManager.deleted_ids == []
    assert 4 in FakeTaskManager.tasks
    assert 9 in FakeTaskManager.tasks
    assert any("has changed since the request" in error.value for error in app.error)
