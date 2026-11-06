from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.core.agent as agent_module
from app.core.agent import SYSTEM_PROMPT, PersonalAssistant, trim_history
from app.core.config import Settings
from app.database.conversation_repository import ConversationRepository


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    config = Settings(
        app_name="PAA",
        api_key="test-key",
        base_url="https://example.com",
        model="test-model",
        debug=False,
        user_tz="Asia/Karachi",
    )
    monkeypatch.setattr(agent_module, "get_settings", lambda: config)
    return config


@pytest.fixture
def client():
    mock = MagicMock()
    mock.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None)
            )
        ]
    )
    return mock


def make_assistant(client, **kwargs):
    return PersonalAssistant(
        client=client,
        task_manager=MagicMock(),
        conversation_repository=ConversationRepository(),
        **kwargs,
    )


def tool_turn(i):
    return [
        {"role": "user", "content": f"u{i}"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": f"c{i}"}]},
        {"role": "tool", "tool_call_id": f"c{i}", "content": "{}"},
        {"role": "assistant", "content": f"a{i}"},
    ]


# ---------- trimming ----------

def test_trim_never_starts_on_orphaned_tool_message():
    history = [{"role": "system", "content": "s"}]
    for i in range(10):
        history += tool_turn(i)

    trimmed = trim_history(history, keep=7)

    assert trimmed[0]["role"] == "system"
    assert trimmed[1]["role"] == "user"

    seen_call_ids = set()
    for message in trimmed[1:]:
        for call in message.get("tool_calls") or []:
            seen_call_ids.add(call["id"])
        if message["role"] == "tool":
            assert message["tool_call_id"] in seen_call_ids


def test_trim_keeps_whole_turn_when_window_has_no_user_message():
    turn = [{"role": "user", "content": "go"}]
    for i in range(10):
        turn += tool_turn(i)[1:3]

    history = [{"role": "system", "content": "s"}] + turn

    assert trim_history(history, keep=5) == history


def test_trim_is_noop_for_short_history():
    history = [{"role": "system", "content": "s"}] + tool_turn(0)

    assert trim_history(history, keep=20) == history


# ---------- system prompt ----------

def test_system_prompt_is_not_persisted(client):
    assistant = make_assistant(client)
    assistant.chat("Hello")

    saved = assistant.conversation_repository.get_history(
        assistant.conversation_id
    )

    assert [m["role"] for m in saved] == ["user", "assistant"]


def test_legacy_system_message_is_replaced_on_load(client):
    repo = ConversationRepository()
    conversation_id = repo.create_conversation()
    repo.save_history(
        conversation_id,
        [
            {"role": "system", "content": "OLD PROMPT"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ],
    )

    assistant = PersonalAssistant(
        client=client,
        task_manager=MagicMock(),
        conversation_id=conversation_id,
        conversation_repository=repo,
    )

    assert assistant.conversation_history[0]["content"] == SYSTEM_PROMPT
    assert len(assistant.conversation_history) == 3


def test_current_time_is_sent_to_model_but_not_stored(client):
    assistant = make_assistant(client)
    assistant.chat("What day is it?")

    sent = client.chat.completions.create.call_args.kwargs["messages"]

    assert sent[0]["role"] == "system"
    assert "Current date and time" in sent[0]["content"]
    assert "Current date and time" not in (
        assistant.conversation_history[0]["content"]
    )


# ---------- lazy conversation creation ----------

def test_no_conversation_row_until_first_message(client):
    assistant = make_assistant(client)

    assert assistant.conversation_id is None
    assert assistant.conversation_repository.list_conversations() == []

    assistant.chat("Hello")

    assert assistant.conversation_id is not None
    assert len(assistant.conversation_repository.list_conversations()) == 1


def test_failed_first_message_creates_no_conversation(client):
    client.chat.completions.create.side_effect = Exception("boom")
    assistant = make_assistant(client)

    with pytest.raises(Exception):
        assistant.chat("Hello")

    assert assistant.conversation_id is None
    assert assistant.conversation_repository.list_conversations() == []