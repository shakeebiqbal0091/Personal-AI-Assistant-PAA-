import pytest

from app.core.config import get_settings
from app.core.llm import create_llm_client
from app.intelligence.intent_classifier import IntentClassifier



@pytest.mark.parametrize(
    "message, expected_intent",
    [
        ("Hey PAA!", "greeting"),

        ("What is artificial intelligence?", "general_question"),
        ("What is Python?", "general_question"),
        ("Who invented computers?", "general_question"),
        ("How does the internet work?", "general_question"),

        ("Explain machine learning.", "explanation"),
        ("Teach me Python.", "explanation"),
        ("Break down neural networks.", "explanation"),
        (
            "Explain this concept step by step.",
            "explanation"
        ),

        ("Add a task to learn Python.", "create_task"),
        ("Show my pending tasks.", "list_tasks"),
        ("Mark task 5 as completed.", "complete_task"),
        ("Delete task 3.", "delete_task"),

        (
            "What task did I mention earlier?",
            "context_query"
        ),
    ]
)
def test_live_intent_classification(message, expected_intent):

    settings = get_settings()
    client = create_llm_client(settings)

    classifier = IntentClassifier(
        client=client,
        model=settings.model
    )

    result = classifier.classify(message)

    print("\nMessage:", message)
    print("Expected:", expected_intent)
    print("Actual:", result.intent.value)
    print("Confidence:", result.confidence)
    print("Entities:", result.entities)

    assert result.intent.value == expected_intent
    assert 0 <= result.confidence <= 1