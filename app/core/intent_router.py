
from dataclasses import dataclass
from typing import Any


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

        raise ValueError("Unable to validate intent.")

    @staticmethod
    def route(intent_name: str, arguments: dict, task_manager):

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
            success = task_manager.delete_task(
                intent.arguments["task_id"]
            )

            return {
                "success": success,
                "intent": intent.name,
                "message": (
                    "Task deleted successfully."
                    if success
                    else "Task not found."
                ),
            }
