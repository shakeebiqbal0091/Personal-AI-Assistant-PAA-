
from dataclasses import dataclass
from typing import Any

from app.database.memory_repository import (
    ALLOWED_MEMORY_CATEGORIES,
    MAX_MEMORY_CONTENT_LENGTH,
)


@dataclass
class Intent:
    name: str
    arguments: dict[str, Any]
    confidence: float = 1.0


class IntentRouter:

    ALLOWED_INTENTS = {
        "create_task",
        "list_tasks",
        "complete_task",
        "delete_task",
        "search_memories",
        "propose_memory",
    }

    @staticmethod
    def validate(intent_name: str, arguments: dict) -> Intent:

        if intent_name not in IntentRouter.ALLOWED_INTENTS:
            raise ValueError(f"Unsupported intent: {intent_name}")

        if not isinstance(arguments, dict):
            raise ValueError("Intent arguments must be an object.")

        if intent_name == "create_task":

            if set(arguments) != {"title", "description"}:
                raise ValueError("Invalid create_task arguments.")

            title = arguments["title"]
            description = arguments["description"]

            if not isinstance(title, str) or not title.strip():
                raise ValueError("Task title cannot be empty.")

            if not isinstance(description, str):
                raise ValueError("Task description must be text.")

            return Intent(
                name=intent_name,
                arguments={
                    "title": title.strip(),
                    "description": description.strip(),
                },
            )

        if intent_name == "list_tasks":

            if set(arguments) != {"status"}:
                raise ValueError("Invalid list_tasks arguments.")

            status = arguments["status"]

            if status not in {"all", "pending", "completed"}:
                raise ValueError("Invalid task status.")

            return Intent(
                name=intent_name,
                arguments={"status": status},
            )

        if intent_name in {"complete_task", "delete_task"}:

            if set(arguments) != {"task_id"}:
                raise ValueError("Invalid task action arguments.")

            task_id = arguments["task_id"]

            # bool is a subclass of int in Python, so reject it explicitly.
            if isinstance(task_id, bool) or not isinstance(task_id, int):
                raise ValueError("Task ID must be an integer.")

            if task_id <= 0:
                raise ValueError("Task ID must be positive.")

            return Intent(
                name=intent_name,
                arguments={"task_id": task_id},
            )

        if intent_name == "search_memories":
            if set(arguments) != {"query"}:
                raise ValueError("Invalid search_memories arguments.")

            query = arguments["query"]
            if not isinstance(query, str):
                raise ValueError("Memory search query must be text.")

            return Intent(
                name=intent_name,
                arguments={"query": query.strip()},
            )

        if intent_name == "propose_memory":
            if set(arguments) != {"content", "category"}:
                raise ValueError("Invalid propose_memory arguments.")

            content = arguments["content"]
            category = arguments["category"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Proposed memory content cannot be empty.")
            if len(content.strip()) > MAX_MEMORY_CONTENT_LENGTH:
                raise ValueError(
                    "Proposed memory content cannot exceed "
                    f"{MAX_MEMORY_CONTENT_LENGTH} characters."
                )
            if category is not None and (
                not isinstance(category, str)
                or category not in ALLOWED_MEMORY_CATEGORIES
            ):
                raise ValueError("Invalid proposed memory category.")

            return Intent(
                name=intent_name,
                arguments={
                    "content": content.strip(),
                    "category": category,
                },
            )

        raise ValueError("Unable to validate intent.")

    @staticmethod
    def route(
        intent_name: str,
        arguments: dict,
        task_manager,
        memory_repository=None,
    ):

        intent = IntentRouter.validate(
            intent_name,
            arguments,
        )

        if intent.name == "create_task":
            task_id = task_manager.create_task(
                intent.arguments["title"],
                intent.arguments["description"],
            )

            return {
                "success": True,
                "intent": intent.name,
                "task_id": task_id,
                "message": "Task created successfully.",
            }

        if intent.name == "list_tasks":
            tasks = task_manager.list_tasks(
                intent.arguments["status"]
            )

            return {
                "success": True,
                "intent": intent.name,
                "tasks": tasks,
                "count": len(tasks),
            }

        if intent.name == "complete_task":
            success = task_manager.complete_task(
                intent.arguments["task_id"]
            )

            return {
                "success": success,
                "intent": intent.name,
                "message": (
                    "Task completed successfully."
                    if success
                    else "Task not found or already completed."
                ),
            }

        if intent.name == "delete_task":
            task_id = intent.arguments["task_id"]
            task = next(
                (
                    task
                    for task in task_manager.list_tasks("all")
                    if task.get("id") == task_id
                ),
                None,
            )

            if task is None:
                return {
                    "success": False,
                    "intent": intent.name,
                    "message": "Task not found.",
                }

            return {
                "success": True,
                "intent": intent.name,
                "pending_confirmation": True,
                "deleted": False,
                "task": {
                    "id": task["id"],
                    "title": task["title"],
                    "description": task.get("description") or "",
                    "status": task["status"],
                },
                "message": (
                    "The task has not been deleted. It is awaiting explicit "
                    "user confirmation in Streamlit."
                ),
            }

        if intent.name == "search_memories":
            if memory_repository is None:
                return {
                    "success": False,
                    "intent": intent.name,
                    "message": "Memory search is unavailable.",
                }

            memories = memory_repository.retrieve_relevant_memories(
                intent.arguments["query"]
            )
            records = [
                {
                    "id": memory["id"],
                    "content": memory["content"],
                    "category": memory["category"],
                    "created_at": memory["created_at"],
                    "updated_at": memory["updated_at"],
                }
                for memory in memories
            ]
            return {
                "success": True,
                "intent": intent.name,
                "memories": records,
                "count": len(records),
                "message": (
                    "Matching saved memory records were found."
                    if records
                    else "No matching saved memory records were found."
                ),
            }

        if intent.name == "propose_memory":
            return {
                "success": True,
                "intent": intent.name,
                "pending_confirmation": True,
                "proposal": intent.arguments,
                "message": (
                    "This memory proposal has not been saved. It requires "
                    "explicit confirmation in Streamlit."
                ),
            }
