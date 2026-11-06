
import pytest

from app.database.db import get_connection
from app.tools.task_manager import TaskManager


@pytest.fixture
def manager(tmp_path):
    db_path = tmp_path / "test_tasks.db"
    return TaskManager(db_path=db_path)


def test_create_task(manager):
    task_id = manager.create_task(
        "Learn Python",
        "Practice Python for one hour."
    )

    tasks = manager.list_tasks()

    assert task_id > 0
    assert len(tasks) == 1
    assert tasks[0]["title"] == "Learn Python"
    assert tasks[0]["status"] == "pending"


def test_reject_empty_task(manager):
    with pytest.raises(ValueError):
        manager.create_task("   ")


def test_filter_tasks(manager):
    manager.create_task("Pending task")
    completed_id = manager.create_task("Completed task")

    manager.complete_task(completed_id)

    assert len(manager.list_tasks("pending")) == 1
    assert len(manager.list_tasks("completed")) == 1
    assert len(manager.list_tasks("all")) == 2


def test_complete_task(manager):
    task_id = manager.create_task("Finish project")

    assert manager.complete_task(task_id) is True
    assert manager.complete_task(task_id) is False

    task = manager.list_tasks()[0]

    assert task["status"] == "completed"
    assert task["completed_at"] is not None


def test_delete_task(manager):
    task_id = manager.create_task("Temporary task")

    assert manager.delete_task(task_id) is True
    assert manager.delete_task(task_id) is False
    assert manager.list_tasks() == []


def test_delete_task_if_unchanged_deletes_matching_snapshot(manager):
    task_id = manager.create_task("Temporary task", "Details")
    task = manager.list_tasks()[0]

    assert manager.delete_task_if_unchanged(
        task_id,
        task["title"],
        task["description"],
        task["status"],
    ) is True
    assert manager.list_tasks() == []


@pytest.mark.parametrize(
    ("field", "changed_value"),
    [
        ("title", "Changed title"),
        ("description", "Changed details"),
        ("status", "completed"),
    ],
)
def test_delete_task_if_unchanged_preserves_changed_task(
    manager, field, changed_value
):
    task_id = manager.create_task("Temporary task", "Details")
    task = manager.list_tasks()[0]
    snapshot = {
        "title": task["title"],
        "description": task["description"],
        "status": task["status"],
    }

    with get_connection(manager.db_path) as connection:
        with connection:
            connection.execute(
                f"UPDATE tasks SET {field} = ? WHERE id = ?",
                (changed_value, task_id),
            )

    assert manager.delete_task_if_unchanged(
        task_id,
        snapshot["title"],
        snapshot["description"],
        snapshot["status"],
    ) is False
    assert len(manager.list_tasks()) == 1


def test_invalid_status(manager):
    with pytest.raises(ValueError):
        manager.list_tasks("invalid")

def test_tasks_persist_after_reinitialization(tmp_path):
    db_path = tmp_path / "persistent_tasks.db"

    first_manager = TaskManager(db_path=db_path)
    first_manager.create_task("Persistent task")

    second_manager = TaskManager(db_path=db_path)

    tasks = second_manager.list_tasks()

    assert len(tasks) == 1
    assert tasks[0]["title"] == "Persistent task"