import json
import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import app.core.agent as agent_module
import app.database.conversation_repository as conversation_repository_module
from app.database.memory_repository import (
    MemoryRepository,
    MAX_MEMORY_CONTENT_LENGTH,
)


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
        self.histories.pop(conversation_id, None)
        return True


class FakeAssistant:
    default_conversation_id = None
    proposal = None
    mode = "success"

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
        if self.proposal is not None:
            call_id = "call_propose_memory"
            arguments = json.dumps(self.proposal)
            self.conversation_history.extend(
                [
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": call_id,
                                "type": "function",
                                "function": {
                                    "name": "propose_memory",
                                    "arguments": arguments,
                                },
                            }
                        ],
                    },
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(
                            {
                                "success": True,
                                "intent": "propose_memory",
                                "pending_confirmation": True,
                                "proposal": self.proposal,
                                "message": (
                                    "This memory proposal has not been saved."
                                ),
                            }
                        ),
                    },
                    {
                        "role": "assistant",
                        "content": "Proposal is awaiting confirmation.",
                    },
                ]
            )
        else:
            self.conversation_history.append(
                {"role": "assistant", "content": "assistant reply"}
            )
        if self.conversation_id is None:
            self.conversation_id = 1
            self.conversation_repository.conversations.append(
                {"id": 1, "title": prompt}
            )
        self.conversation_repository.histories[self.conversation_id] = (
            self.conversation_history[1:]
        )
        return "assistant reply"

    def reset_conversation(self):
        self.conversation_history = [
            {"role": "system", "content": "system prompt"}
        ]


def _run_app(monkeypatch):
    FakeConversationRepository.conversations = []
    FakeConversationRepository.histories = {}
    FakeAssistant.default_conversation_id = None
    FakeAssistant.proposal = None
    FakeAssistant.mode = "success"
    monkeypatch.setattr(agent_module, "PersonalAssistant", FakeAssistant)
    monkeypatch.setattr(
        conversation_repository_module,
        "ConversationRepository",
        FakeConversationRepository,
    )
    return AppTest.from_file(
        str(Path(__file__).parents[1] / "app" / "main.py")
    ).run()


def _submit_memory_proposal(app, content, category="preference"):
    FakeAssistant.proposal = {
        "content": content,
        "category": category,
    }
    app.chat_input[0].set_value(
        f"Remember that {content}"
    ).run()
    return app.session_state.pending_memory_proposal


def _memory_repository(app):
    return app.session_state.memory_repository


def _create_memory(app, content, category=None):
    return _memory_repository(app).create_memory(content, category)


def test_memory_management_ui_renders(monkeypatch):
    app = _run_app(monkeypatch)

    assert any(
        "Personal Reference Notes" in element.value for element in app.subheader
    )
    assert any(
        "No personal reference notes have been saved." in element.value
        for element in app.info
    )
    assert any(button.label == "Save Memory" for button in app.button)
    assert any(
        "limited selection may be included in requests sent to the configured "
        "AI provider" in element.value
        and "not all notes are sent" in element.value
        for element in app.caption
    )
    assert not app.exception


def test_user_can_create_memory_and_saved_content_is_shown(monkeypatch):
    app = _run_app(monkeypatch)
    app.text_area(key="memory_create_content").set_value(
        "Prefers morning meetings"
    )
    app.selectbox(key="memory_create_category").select("preference")
    app.button(key="FormSubmitter:create_memory_form-Save Memory").click().run()

    memories = _memory_repository(app).list_memories()
    assert len(memories) == 1
    assert memories[0]["content"] == "Prefers morning meetings"
    assert memories[0]["category"] == "preference"
    assert any(
        "Saved memory #1: Prefers morning meetings" in element.value
        for element in app.success
    )
    assert any(
        "Memory #1 — preference" in element.label for element in app.expander
    )
    assert any(
        "Prefers morning meetings" in element.value for element in app.markdown
    )


def test_duplicate_creation_reports_existing_memory_without_new_record(
    monkeypatch,
):
    app = _run_app(monkeypatch)
    app.text_area(key="memory_create_content").set_value("Keep this note")
    app.button(key="FormSubmitter:create_memory_form-Save Memory").click().run()

    app.text_area(key="memory_create_content").set_value("  KEEP  this note ")
    app.button(key="FormSubmitter:create_memory_form-Save Memory").click().run()

    assert len(_memory_repository(app).list_memories()) == 1
    assert any(
        "identical memory already exists as #1" in element.value
        for element in app.info
    )
    assert not any(
        "Saved memory #1:" in element.value for element in app.success
    )


def test_user_can_edit_memory(monkeypatch):
    app = _run_app(monkeypatch)
    memory_id = _create_memory(app, "Old note", "fact")
    app.run()
    content_key = next(
        element.key for element in app.text_area if element.label == "Content"
    )
    category_key = next(
        element.key
        for element in app.selectbox
        if element.key.startswith("memory_edit_category_")
    )
    app.text_area(key=content_key).set_value("Updated note")
    app.selectbox(key=category_key).select("project")
    app.button(key="FormSubmitter:edit_memory_form-Save Changes").click().run()

    updated = _memory_repository(app).get_memory(memory_id)
    assert updated["content"] == "Updated note"
    assert updated["category"] == "project"
    assert any(
        f"Updated memory #{memory_id}" in element.value
        for element in app.success
    )


def test_invalid_memory_update_shows_error(monkeypatch):
    app = _run_app(monkeypatch)
    memory_id = _create_memory(app, "Keep note", "fact")
    app.run()
    content_key = next(
        element.key for element in app.text_area if element.label == "Content"
    )
    app.text_area(key=content_key).set_value("   ")
    app.button(key="FormSubmitter:edit_memory_form-Save Changes").click().run()

    assert _memory_repository(app).get_memory(memory_id)["content"] == (
        "Keep note"
    )
    assert any(
        "Memory content cannot be empty" in element.value
        for element in app.error
    )


def test_requesting_delete_targets_exact_memory(monkeypatch):
    app = _run_app(monkeypatch)
    first_id = _create_memory(app, "First memory")
    second_id = _create_memory(app, "Second memory")
    app.run()
    app.selectbox(key="memory_delete_selection").select(second_id)
    app.button(key="request_memory_delete").click().run()

    assert app.session_state.pending_memory_deletion["id"] == second_id
    assert _memory_repository(app).get_memory(first_id) is not None
    assert _memory_repository(app).get_memory(second_id) is not None
    assert any(
        f"Confirm deletion of memory #{second_id}" in element.value
        for element in app.warning
    )


def test_cancel_delete_leaves_memory_database_unchanged(monkeypatch):
    app = _run_app(monkeypatch)
    memory_id = _create_memory(app, "Keep after cancel")
    app.run()
    app.button(key="request_memory_delete").click().run()
    before = _memory_repository(app).get_memory(memory_id)

    app.button(key="cancel_memory_deletion").click().run()

    assert _memory_repository(app).get_memory(memory_id) == before
    assert app.session_state.pending_memory_deletion is None


def test_confirm_delete_removes_only_selected_memory(monkeypatch):
    app = _run_app(monkeypatch)
    keep_id = _create_memory(app, "Keep this memory")
    delete_id = _create_memory(app, "Delete this memory")
    app.run()
    app.selectbox(key="memory_delete_selection").select(delete_id)
    app.button(key="request_memory_delete").click().run()
    app.button(key="confirm_memory_deletion").click().run()

    assert _memory_repository(app).get_memory(delete_id) is None
    assert _memory_repository(app).get_memory(keep_id)["content"] == (
        "Keep this memory"
    )
    assert app.session_state.pending_memory_deletion is None
    assert any(
        f"Deleted memory #{delete_id}" in element.value
        for element in app.success
    )


def test_stale_edit_selection_is_handled_without_overwriting(monkeypatch):
    app = _run_app(monkeypatch)
    memory_id = _create_memory(app, "Original note")
    app.run()
    content_key = next(
        element.key for element in app.text_area if element.label == "Content"
    )
    app.text_area(key=content_key).set_value("Unsaved edit")
    repository = _memory_repository(app)
    original_update = repository.update_memory

    def update_after_concurrent_change(target_id, **kwargs):
        MemoryRepository(db_path=repository.db_path).update_memory(
            target_id,
            content="Changed elsewhere",
        )
        return original_update(target_id, **kwargs)

    monkeypatch.setattr(
        repository,
        "update_memory",
        update_after_concurrent_change,
    )

    app.button(key="FormSubmitter:edit_memory_form-Save Changes").click().run()

    assert _memory_repository(app).get_memory(memory_id)["content"] == (
        "Changed elsewhere"
    )
    assert any(
        f"Memory #{memory_id} changed while you were editing"
        in element.value
        for element in app.error
    )


def test_stale_delete_confirmation_does_not_delete_changed_memory(monkeypatch):
    app = _run_app(monkeypatch)
    memory_id = _create_memory(app, "Original note")
    app.run()
    app.button(key="request_memory_delete").click().run()
    repository = _memory_repository(app)
    original_delete = repository.delete_memory_if_unchanged

    def delete_after_concurrent_change(target_id, **kwargs):
        MemoryRepository(db_path=repository.db_path).update_memory(
            target_id,
            content="Changed note",
        )
        return original_delete(target_id, **kwargs)

    monkeypatch.setattr(
        repository,
        "delete_memory_if_unchanged",
        delete_after_concurrent_change,
    )

    app.button(key="confirm_memory_deletion").click().run()

    assert _memory_repository(app).get_memory(memory_id)["content"] == (
        "Changed note"
    )
    assert app.session_state.pending_memory_deletion is None
    assert any(
        "changed before deletion" in element.value
        for element in app.error
    )


def test_missing_memory_at_confirmation_is_reported_without_deleting_others(
    monkeypatch,
):
    app = _run_app(monkeypatch)
    missing_id = _create_memory(app, "Remove externally")
    remaining_id = _create_memory(app, "Keep this memory")
    app.run()
    app.selectbox(key="memory_delete_selection").select(missing_id)
    app.button(key="request_memory_delete").click().run()
    _memory_repository(app).delete_memory(missing_id)

    app.button(key="confirm_memory_deletion").click().run()

    assert _memory_repository(app).get_memory(missing_id) is None
    assert _memory_repository(app).get_memory(remaining_id)["content"] == (
        "Keep this memory"
    )
    assert app.session_state.pending_memory_deletion is None
    assert any(
        f"Memory #{missing_id} no longer exists" in element.value
        for element in app.error
    )


def test_memory_persists_across_streamlit_reruns(monkeypatch):
    app = _run_app(monkeypatch)
    app.text_area(key="memory_create_content").set_value("Persist this note")
    app.button(key="FormSubmitter:create_memory_form-Save Memory").click().run()
    app.run()

    assert any(
        "Persist this note" in element.value for element in app.markdown
    )
    assert len(_memory_repository(app).list_memories()) == 1


def test_switching_conversations_does_not_affect_global_memories(monkeypatch):
    app = _run_app(monkeypatch)
    memory_id = _create_memory(app, "Global preference", "preference")
    FakeConversationRepository.conversations = [
        {"id": 1, "title": "First"},
        {"id": 2, "title": "Second"},
    ]
    app.run()

    app.selectbox(key="conversation_select_None").select("First (#1)").run()
    app.selectbox(key="conversation_select_1").select("Second (#2)").run()

    assert _memory_repository(app).get_memory(memory_id)["content"] == (
        "Global preference"
    )


def test_ordinary_chat_does_not_create_memories(monkeypatch):
    app = _run_app(monkeypatch)
    app.chat_input[0].set_value(
        "I prefer quiet mornings. Please help me plan my day."
    ).run()

    assert _memory_repository(app).list_memories() == []
    assert not app.exception


def test_chat_proposal_requires_confirmation_and_saves_exact_content(
    monkeypatch,
):
    app = _run_app(monkeypatch)
    content = "I prefer concise answers, without extra details."
    proposal = _submit_memory_proposal(app, content)

    assert proposal is not None
    assert proposal["content"] == content
    assert proposal["category"] == "preference"
    assert proposal["conversation_id"] == 1
    assert proposal["operation_id"]
    assert _memory_repository(app).list_memories() == []
    assert any(content in element.value for element in app.markdown)
    assert any(
        "Review this exact proposal" in warning.value
        and "Personal Memories" in warning.value
        for warning in app.warning
    )
    assert any(button.label == "Confirm Save" for button in app.button)
    assert any(button.label == "Cancel" for button in app.button)

    confirm_key = f"confirm_save_memory_{proposal['operation_id']}"
    app.button(key=confirm_key).click().run()

    memories = _memory_repository(app).list_memories()
    assert len(memories) == 1
    assert memories[0]["content"] == content
    assert memories[0]["category"] == "preference"
    assert app.session_state.pending_memory_proposal is None
    assert any(
        "Saved memory #1 to Personal Memories" in success.value
        for success in app.success
    )

    app.run()
    assert len(_memory_repository(app).list_memories()) == 1
    assert not any(button.label == "Confirm Save" for button in app.button)


def test_canceling_chat_proposal_does_not_save(monkeypatch):
    app = _run_app(monkeypatch)
    proposal = _submit_memory_proposal(app, "Prefers morning meetings")

    app.button(
        key=f"cancel_save_memory_{proposal['operation_id']}"
    ).click().run()

    assert _memory_repository(app).list_memories() == []
    assert app.session_state.pending_memory_proposal is None
    assert any(
        "Proposal cancelled; no memory was saved" in info.value
        for info in app.info
    )


def test_chat_proposal_duplicate_preserves_existing_memory(monkeypatch):
    app = _run_app(monkeypatch)
    existing_id = _create_memory(app, "Prefers concise answers", "fact")
    proposal = _submit_memory_proposal(
        app,
        "PREFERS concise answers",
        "preference",
    )

    app.button(
        key=f"confirm_save_memory_{proposal['operation_id']}"
    ).click().run()

    assert len(_memory_repository(app).list_memories()) == 1
    existing = _memory_repository(app).get_memory(existing_id)
    assert existing["content"] == "Prefers concise answers"
    assert existing["category"] == "fact"
    assert any(
        f"identical memory already exists as #{existing_id}"
        in info.value
        for info in app.info
    )
    assert not any("Saved memory #" in success.value for success in app.success)


@pytest.mark.parametrize(
    "content,category",
    [
        (" ", "fact"),
        ("Valid content", "unsupported"),
        ("x" * (MAX_MEMORY_CONTENT_LENGTH + 1), None),
    ],
)
def test_invalid_chat_proposal_is_not_approvable(
    monkeypatch,
    content,
    category,
):
    app = _run_app(monkeypatch)
    proposal = _submit_memory_proposal(app, content, category)

    assert proposal is None
    assert _memory_repository(app).list_memories() == []
    assert not any(button.label == "Confirm Save" for button in app.button)


def test_new_proposal_invalidates_stale_approval(monkeypatch):
    app = _run_app(monkeypatch)
    old_proposal = _submit_memory_proposal(app, "Old proposal")
    old_operation_id = old_proposal["operation_id"]

    new_proposal = _submit_memory_proposal(app, "Replacement proposal")

    assert new_proposal["operation_id"] != old_operation_id
    assert new_proposal["content"] == "Replacement proposal"
    assert not any(
        button.key == f"confirm_save_memory_{old_operation_id}"
        for button in app.button
    )
    app.button(
        key=f"confirm_save_memory_{new_proposal['operation_id']}"
    ).click().run()

    memories = _memory_repository(app).list_memories()
    assert [memory["content"] for memory in memories] == [
        "Replacement proposal"
    ]


def test_failed_new_chat_does_not_restore_invalidated_proposal(monkeypatch):
    app = _run_app(monkeypatch)
    proposal = _submit_memory_proposal(app, "Earlier-turn proposal")
    assert proposal["content"] == "Earlier-turn proposal"

    FakeAssistant.mode = "fail_before_checkpoint"
    app.chat_input[0].set_value("A new request that fails").run()

    assert app.session_state.pending_memory_proposal is None
    assert not any(button.label == "Confirm Save" for button in app.button)
    assert _memory_repository(app).list_memories() == []
    assert any(
        "request failed before checkpoint" in error.value
        for error in app.error
    )
    assert any(
        message["role"] == "tool"
        and "Earlier-turn proposal" in message["content"]
        for message in app.session_state.assistant.conversation_history
    )


def test_switching_conversations_invalidates_chat_proposal(monkeypatch):
    app = _run_app(monkeypatch)
    proposal = _submit_memory_proposal(app, "Conversation-specific proposal")
    FakeConversationRepository.conversations.append(
        {"id": 2, "title": "Second"}
    )
    app.run()

    app.selectbox(key="conversation_select_1").select("Second (#2)").run()

    assert app.session_state.pending_memory_proposal is None
    assert not any(
        button.key == f"confirm_save_memory_{proposal['operation_id']}"
        for button in app.button
    )
    assert _memory_repository(app).list_memories() == []


@pytest.mark.parametrize(
    "control_label",
    ["➕ New Conversation", "Clear Current Conversation", "🗑️ Delete Current Conversation"],
)
def test_conversation_lifecycle_invalidates_chat_proposal(
    monkeypatch,
    control_label,
):
    app = _run_app(monkeypatch)
    proposal = _submit_memory_proposal(app, "Pending proposal")

    next(
        button for button in app.button if button.label == control_label
    ).click().run()

    assert app.session_state.pending_memory_proposal is None
    assert not any(
        button.key == f"confirm_save_memory_{proposal['operation_id']}"
        for button in app.button
    )
    assert _memory_repository(app).list_memories() == []


def test_pending_proposal_is_not_reconstructed_after_session_restart(
    monkeypatch,
):
    app = _run_app(monkeypatch)
    proposal = _submit_memory_proposal(app, "Transient approval")
    persisted_history = list(
        FakeConversationRepository.histories[proposal["conversation_id"]]
    )

    FakeConversationRepository.histories[proposal["conversation_id"]] = (
        persisted_history
    )
    FakeAssistant.default_conversation_id = proposal["conversation_id"]
    restarted_app = AppTest.from_file(
        str(Path(__file__).parents[1] / "app" / "main.py")
    ).run()

    assert restarted_app.session_state.pending_memory_proposal is None
    assert not any(
        button.label == "Confirm Save" for button in restarted_app.button
    )
    assert _memory_repository(restarted_app).list_memories() == []

    FakeAssistant.mode = "fail_before_checkpoint"
    restarted_app.chat_input[0].set_value(
        "A request that fails after restart"
    ).run()

    assert restarted_app.session_state.pending_memory_proposal is None
    assert not any(
        button.label == "Confirm Save" for button in restarted_app.button
    )
    assert _memory_repository(restarted_app).list_memories() == []
    assert any(
        "request failed before checkpoint" in error.value
        for error in restarted_app.error
    )


def test_repository_failure_does_not_report_chat_proposal_success(
    monkeypatch,
):
    app = _run_app(monkeypatch)
    proposal = _submit_memory_proposal(app, "Failure should not save")
    repository = _memory_repository(app)

    def fail_creation(content, category):
        raise sqlite3.OperationalError("database unavailable")

    monkeypatch.setattr(repository, "create_memory_with_status", fail_creation)
    app.button(
        key=f"confirm_save_memory_{proposal['operation_id']}"
    ).click().run()

    assert app.session_state.pending_memory_proposal is None
    assert any(
        "Could not save the proposed memory: database unavailable"
        in error.value
        for error in app.error
    )
    assert not any(
        "Saved memory #" in success.value for success in app.success
    )
    assert repository.list_memories() == []
