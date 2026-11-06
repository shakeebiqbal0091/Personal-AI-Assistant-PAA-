from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.core.agent as agent_module
from app.core.config import Settings
from app.core.agent import PersonalAssistant


@pytest.fixture
def settings(monkeypatch):
    config = Settings(
        app_name="Personal AI Assistant",
        api_key="test-key",
        base_url="https://example.com",
        model="test-model",
        debug=False,
    )

    monkeypatch.setattr(
        agent_module,
        "get_settings",
        lambda: config
    )

    return config


@pytest.fixture
def mock_client():
    client = MagicMock()

    client.chat.completions.create.return_value.choices = [
        SimpleNamespace(
            message=SimpleNamespace(content="Hello! How can I help?")
        )
    ]

    return client


def test_agent_returns_ai_response(settings, mock_client):
    assistant = PersonalAssistant(client=mock_client)

    response = assistant.chat("Hello")

    assert response == "Hello! How can I help?"
    assert len(assistant.conversation_history) == 3


def test_agent_rejects_empty_message(settings, mock_client):
    assistant = PersonalAssistant(client=mock_client)

    with pytest.raises(ValueError):
        assistant.chat("   ")

    mock_client.chat.completions.create.assert_not_called()


def test_agent_reset_conversation(settings, mock_client):
    assistant = PersonalAssistant(client=mock_client)

    assistant.chat("Hello")
    assistant.reset_conversation()

    assert len(assistant.conversation_history) == 1
    assert assistant.conversation_history[0]["role"] == "system"


def test_agent_handles_api_error(settings, mock_client):
    assistant = PersonalAssistant(client=mock_client)

    mock_client.chat.completions.create.side_effect = Exception(
        "API connection failed"
    )

    with pytest.raises(Exception):
        assistant.chat("Hello")

    assert len(assistant.conversation_history) == 1