
from app.core.agent import SYSTEM_PROMPT


def test_prompt_contains_context_resolution():
    assert "CONTEXT RESOLUTION" in SYSTEM_PROMPT
    assert "conversation history" in SYSTEM_PROMPT.lower()


def test_prompt_handles_ambiguous_requests():
    assert "AMBIGUITY HANDLING" in SYSTEM_PROMPT
    assert "clarification" in SYSTEM_PROMPT.lower()


def test_prompt_prevents_invented_task_ids():
    assert "Never invent or guess a task ID" in SYSTEM_PROMPT


def test_prompt_handles_task_references():
    assert '"it"' in SYSTEM_PROMPT
    assert '"that task"' in SYSTEM_PROMPT
    assert '"the first one"' in SYSTEM_PROMPT


def test_prompt_has_deletion_safety_rules():
    assert "Deleting a task is a destructive action" in SYSTEM_PROMPT
