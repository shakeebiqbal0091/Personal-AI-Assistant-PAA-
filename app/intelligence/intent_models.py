
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class IntentType(str, Enum):

    GREETING = "greeting"

    GENERAL_QUESTION = "general_question"

    EXPLANATION = "explanation"

    CREATE_TASK = "create_task"

    LIST_TASKS = "list_tasks"

    COMPLETE_TASK = "complete_task"

    DELETE_TASK = "delete_task"

    CONTEXT_QUERY = "context_query"

    CLARIFICATION = "clarification"

    UNKNOWN = "unknown"


class IntentResult(BaseModel):

    intent: IntentType

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=0.0
    )

    entities: dict[str, Any] = Field(
        default_factory=dict
    )

    requires_clarification: bool = False

    clarification_question: Optional[str] = None