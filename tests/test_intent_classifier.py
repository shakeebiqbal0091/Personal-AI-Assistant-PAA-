
import json
from unittest.mock import MagicMock

import pytest

from app.intelligence.intent_classifier import IntentClassifier
from app.intelligence.intent_models import IntentType


@pytest.fixture
def mock_client():

    client = MagicMock()

    return client


@pytest.fixture
def classifier(mock_client):

    return IntentClassifier(
        client=mock_client,
        model="test-model"
    )


def mock_response(client, result):

    response = MagicMock()

    response.choices[0].message.content = json.dumps(result)

    client.chat.completions.create.return_value = response


def test_greeting_intent(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "greeting",
        "confidence": 0.99,
        "entities": {},
        "requires_clarification": False,
        "clarification_question": None
    })

    result = classifier.classify("Hey PAA!")

    assert result.intent == IntentType.GREETING
    assert result.confidence >= 0.9


def test_general_question_intent(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "general_question",
        "confidence": 0.98,
        "entities": {},
        "requires_clarification": False,
        "clarification_question": None
    })

    result = classifier.classify(
        "What is artificial intelligence?"
    )

    assert result.intent == IntentType.GENERAL_QUESTION


def test_explanation_intent(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "explanation",
        "confidence": 0.97,
        "entities": {
            "topic": "machine learning"
        },
        "requires_clarification": False,
        "clarification_question": None
    })

    result = classifier.classify(
        "Explain machine learning."
    )

    assert result.intent == IntentType.EXPLANATION


def test_create_task_intent(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "create_task",
        "confidence": 0.98,
        "entities": {
            "title": "Learn Python"
        },
        "requires_clarification": False,
        "clarification_question": None
    })

    result = classifier.classify(
        "Add a task to learn Python."
    )

    assert result.intent == IntentType.CREATE_TASK
    assert result.entities["title"] == "Learn Python"


def test_list_tasks_intent(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "list_tasks",
        "confidence": 0.98,
        "entities": {
            "status": "pending"
        },
        "requires_clarification": False,
        "clarification_question": None
    })

    result = classifier.classify(
        "Show my pending tasks."
    )

    assert result.intent == IntentType.LIST_TASKS
    assert result.entities["status"] == "pending"


def test_complete_task_intent(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "complete_task",
        "confidence": 0.98,
        "entities": {
            "task_id": 5
        },
        "requires_clarification": False,
        "clarification_question": None
    })

    result = classifier.classify(
        "Mark task 5 as completed."
    )

    assert result.intent == IntentType.COMPLETE_TASK
    assert result.entities["task_id"] == 5


def test_delete_task_intent(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "delete_task",
        "confidence": 0.98,
        "entities": {
            "task_id": 3
        },
        "requires_clarification": False,
        "clarification_question": None
    })

    result = classifier.classify(
        "Delete task 3."
    )

    assert result.intent == IntentType.DELETE_TASK
    assert result.entities["task_id"] == 3


def test_context_query_intent(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "context_query",
        "confidence": 0.95,
        "entities": {},
        "requires_clarification": False,
        "clarification_question": None
    })

    result = classifier.classify(
        "What task did I mention earlier?"
    )

    assert result.intent == IntentType.CONTEXT_QUERY


def test_clarification_intent(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "clarification",
        "confidence": 0.95,
        "entities": {},
        "requires_clarification": True,
        "clarification_question": "Which task do you want to delete?"
    })

    result = classifier.classify("Delete that one.")

    assert result.intent == IntentType.CLARIFICATION
    assert result.requires_clarification is True
    assert result.clarification_question is not None


def test_unknown_intent(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "unknown",
        "confidence": 0.25,
        "entities": {},
        "requires_clarification": False,
        "clarification_question": None
    })

    result = classifier.classify(
        "Do something with the thing."
    )

    assert result.intent == IntentType.UNKNOWN


def test_empty_message_rejected(classifier):

    with pytest.raises(ValueError):

        classifier.classify("   ")


def test_invalid_json_response(classifier, mock_client):

    response = MagicMock()

    response.choices[0].message.content = "invalid json"

    mock_client.chat.completions.create.return_value = response

    with pytest.raises(RuntimeError):

        classifier.classify("Hello")


def test_missing_response_rejected(classifier, mock_client):

    response = MagicMock()

    response.choices[0].message.content = None

    mock_client.chat.completions.create.return_value = response

    with pytest.raises(RuntimeError):

        classifier.classify("Hello")


def test_classifier_receives_conversation_context(
    classifier,
    mock_client
):

    mock_response(mock_client, {
        "intent": "complete_task",
        "confidence": 0.95,
        "entities": {
            "task_id": 5
        },
        "requires_clarification": False,
        "clarification_question": None
    })

    classifier.classify(
        "Complete that task.",
        conversation_context="Previous task: Learn Python, ID 5"
    )

    call_args = mock_client.chat.completions.create.call_args

    messages = call_args.kwargs["messages"]

    user_content = json.loads(messages[1]["content"])

    assert user_content["conversation_context"] == (
        "Previous task: Learn Python, ID 5"
    )


def test_invalid_confidence_rejected(classifier, mock_client):

    mock_response(mock_client, {
        "intent": "greeting",
        "confidence": 1.5,
        "entities": {},
        "requires_clarification": False,
        "clarification_question": None
    })

    with pytest.raises(RuntimeError):

        classifier.classify("Hello")