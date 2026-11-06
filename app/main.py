import json
import sqlite3

import streamlit as st

from app.core.agent import PersonalAssistant
from app.tools.task_manager import TaskManager
from app.database.conversation_repository import ConversationRepository


st.set_page_config(
    page_title="Personal AI Assistant",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 Personal AI Assistant")
st.caption("Your intelligent assistant for everyday life.")

NEW_CONVERSATION_LABEL = "✏️ New conversation (unsaved)"


def _displayable_chat_messages(history):
    return [
        message
        for message in history
        if message.get("content")
        and (
            message.get("role") == "user"
            or (
                message.get("role") == "assistant"
                and not message.get("tool_calls")
            )
        )
    ]


def _pending_deletions_from_history(history, conversation_id):
    last_user_index = next(
        (
            index
            for index in range(len(history) - 1, -1, -1)
            if history[index].get("role") == "user"
        ),
        None,
    )
    if last_user_index is None or conversation_id is None:
        return []

    pending = []
    for message in history[last_user_index + 1:]:
        if message.get("role") != "tool":
            continue

        try:
            result = json.loads(message.get("content", ""))
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(result, dict):
            continue

        task = result.get("task")
        if (
            result.get("intent") != "delete_task"
            or result.get("pending_confirmation") is not True
            or not isinstance(task, dict)
            or isinstance(task.get("id"), bool)
            or not isinstance(task.get("id"), int)
            or task["id"] <= 0
            or not isinstance(task.get("title"), str)
            or not task["title"]
            or not isinstance(message.get("tool_call_id"), str)
            or not message["tool_call_id"]
        ):
            continue

        pending.append({
            "conversation_id": conversation_id,
            "tool_call_id": message.get("tool_call_id"),
            "task": {
                "id": task["id"],
                "title": task["title"],
                "description": (
                    task.get("description")
                    if isinstance(task.get("description"), str)
                    else ""
                ),
                "status": (
                    task.get("status")
                    if isinstance(task.get("status"), str)
                    else "unknown"
                ),
            },
        })

    return pending


def _clear_pending_deletions():
    st.session_state.pending_task_deletions = []
    st.session_state.pop("pending_deletion_notice", None)


# ----------------------------------
# INITIALIZE APPLICATION COMPONENTS
# ----------------------------------

if "conversation_repository" not in st.session_state:
    st.session_state.conversation_repository = ConversationRepository()

if "assistant" not in st.session_state:
    try:
        st.session_state.assistant = PersonalAssistant(
            conversation_repository=st.session_state.conversation_repository
        )
        st.session_state.messages = []

    except Exception as error:
        st.error(f"Assistant initialization failed: {error}")
        st.stop()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_task_deletions" not in st.session_state:
    st.session_state.pending_task_deletions = []

if "task_manager" not in st.session_state:
    st.session_state.task_manager = TaskManager()


# ----------------------------------
# CONVERSATION HISTORY SIDEBAR
# ----------------------------------

with st.sidebar:
    st.header("Conversation History")

    repository = st.session_state.conversation_repository
    conversations = repository.list_conversations()

    if st.button("➕ New Conversation", use_container_width=True):
        _clear_pending_deletions()
        st.session_state.assistant = PersonalAssistant(
            conversation_repository=repository
        )
        st.session_state.messages = []
        st.rerun()

    current_id = st.session_state.assistant.conversation_id

    if conversations:
        conversation_options = {
            f"{item['title']} (#{item['id']})": item["id"]
            for item in conversations
        }

        labels = list(conversation_options.keys())

        if current_id is None:
            labels = [NEW_CONVERSATION_LABEL] + labels
            index = 0
        else:
            index = next(
                (
                    i for i, label in enumerate(labels)
                    if conversation_options[label] == current_id
                ),
                0,
            )

        selected_label = st.selectbox(
            "Previous Conversations",
            labels,
            index=index,
            key=f"conversation_select_{current_id}",
        )

        selected_id = conversation_options.get(selected_label)

        if selected_id is not None and selected_id != current_id:
            _clear_pending_deletions()
            st.session_state.assistant = PersonalAssistant(
                conversation_id=selected_id,
                conversation_repository=repository,
            )

            st.session_state.messages = _displayable_chat_messages(
                st.session_state.assistant.conversation_history
            )

            st.rerun()

    if current_id is not None and st.button("🗑️ Delete Current Conversation"):
        _clear_pending_deletions()
        repository.delete_conversation(current_id)

        st.session_state.assistant = PersonalAssistant(
            conversation_repository=repository
        )
        st.session_state.messages = []
        st.rerun()

    st.divider()

    if st.button("Clear Current Conversation", use_container_width=True):
        _clear_pending_deletions()
        st.session_state.assistant.reset_conversation()
        st.session_state.messages = []
        st.rerun()


# ----------------------------------
# APPLICATION TABS
# ----------------------------------

assistant_tab, tasks_tab = st.tabs(
    ["💬 Chat Assistant", "📋 My Tasks"]
)


# ----------------------------------
# CHAT ASSISTANT
# ----------------------------------

with assistant_tab:

    st.subheader("Chat with your Personal AI Assistant")

    # Chat input
    prompt = st.chat_input("Message your Personal AI Assistant...")

    if prompt:

        is_first_message = (
            st.session_state.assistant.conversation_id is None
        )
        chat_succeeded = False

        try:
            with st.spinner("Thinking..."):
                st.session_state.assistant.chat(prompt)
            chat_succeeded = True
        except Exception as error:
            st.error(f"Something went wrong: {error}")
        finally:
            st.session_state.messages = _displayable_chat_messages(
                st.session_state.assistant.conversation_history
            )
            new_pending = _pending_deletions_from_history(
                st.session_state.assistant.conversation_history,
                st.session_state.assistant.conversation_id,
            )
            if new_pending:
                existing_call_ids = {
                    item["tool_call_id"]
                    for item in st.session_state.pending_task_deletions
                }
                st.session_state.pending_task_deletions.extend(
                    item
                    for item in new_pending
                    if item["tool_call_id"] not in existing_call_ids
                )

        if (
            chat_succeeded
            and st.session_state.assistant.conversation_id is not None
        ):
            # Refresh sidebar after first conversation is created
            if is_first_message:
                st.rerun()

    # Agent history is authoritative, including after failed requests.
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    assistant_conversation_id = (
        st.session_state.assistant.conversation_id
    )
    current_pending = [
        item
        for item in st.session_state.pending_task_deletions
        if item["conversation_id"] == assistant_conversation_id
    ]
    if len(current_pending) != len(st.session_state.pending_task_deletions):
        st.session_state.pending_task_deletions = current_pending

    notice = st.session_state.pop("pending_deletion_notice", None)
    if notice is not None:
        if notice["kind"] == "error":
            st.error(notice["message"])
        else:
            st.success(notice["message"])

    for pending in current_pending:
        task = pending["task"]
        st.warning(
            f"Deletion requires your approval: **{task['title']}** "
            f"(Task #{task['id']}, {task['status']}). "
            "This task has not been deleted."
        )
        if task["description"]:
            st.write(task["description"])

        confirm_column, cancel_column = st.columns(2)
        confirm_key = f"confirm_delete_{pending['tool_call_id']}"
        cancel_key = f"cancel_delete_{pending['tool_call_id']}"

        if confirm_column.button("Confirm Delete", key=confirm_key):
            try:
                current_task = next(
                    (
                        item
                        for item in st.session_state.task_manager.list_tasks(
                            "all"
                        )
                        if item.get("id") == task["id"]
                    ),
                    None,
                )
                if current_task is None:
                    st.session_state.pending_deletion_notice = {
                        "kind": "error",
                        "message": (
                            f"Task #{task['id']} no longer exists; "
                            "nothing was deleted."
                        ),
                    }
                    clear_request = True
                elif any(
                    current_task.get(field) != task[field]
                    for field in ("title", "description", "status")
                ):
                    st.session_state.pending_deletion_notice = {
                        "kind": "error",
                        "message": (
                            f"Task #{task['id']} has changed since the "
                            "request; nothing was deleted. Ask the assistant "
                            "to request deletion again."
                        ),
                    }
                    clear_request = True
                elif st.session_state.task_manager.delete_task_if_unchanged(
                    task["id"],
                    task["title"],
                    task["description"],
                    task["status"],
                ):
                    st.session_state.pending_deletion_notice = {
                        "kind": "success",
                        "message": f"Task #{task['id']} deleted.",
                    }
                    clear_request = True
                else:
                    st.session_state.pending_deletion_notice = {
                        "kind": "error",
                        "message": (
                            f"Task #{task['id']} no longer exists or has changed; "
                            "nothing was deleted. Ask the assistant to request "
                            "deletion again."
                        ),
                    }
                    clear_request = True
            except sqlite3.Error as error:
                st.session_state.pending_deletion_notice = {
                    "kind": "error",
                    "message": (
                        f"Could not delete task #{task['id']}: {error}"
                    ),
                }
                clear_request = False

            if clear_request:
                st.session_state.pending_task_deletions = [
                    item
                    for item in st.session_state.pending_task_deletions
                    if item["tool_call_id"] != pending["tool_call_id"]
                ]
            st.rerun()

        if cancel_column.button("Cancel", key=cancel_key):
            st.session_state.pending_task_deletions = [
                item
                for item in st.session_state.pending_task_deletions
                if item["tool_call_id"] != pending["tool_call_id"]
            ]
            st.rerun()


# ----------------------------------
# TASK MANAGEMENT
# ----------------------------------

with tasks_tab:

    manager = st.session_state.task_manager

    st.subheader("Manage Your Daily Tasks")

    # Create task
    with st.form("create_task_form"):

        task_title = st.text_input("Task title")
        task_description = st.text_area("Description (optional)")

        submitted = st.form_submit_button(
            "Create Task",
            use_container_width=True,
        )

        if submitted:
            try:
                task_id = manager.create_task(
                    task_title,
                    task_description,
                )

                st.success(f"Task #{task_id} created successfully!")
                st.rerun()

            except ValueError as error:
                st.error(str(error))

    st.divider()

    # Task statistics
    all_tasks = manager.list_tasks("all")
    pending_tasks = manager.list_tasks("pending")
    completed_tasks = manager.list_tasks("completed")

    col1, col2, col3 = st.columns(3)

    col1.metric("Total Tasks", len(all_tasks))
    col2.metric("Pending", len(pending_tasks))
    col3.metric("Completed", len(completed_tasks))

    st.divider()

    # Pending tasks
    st.subheader("⏳ Pending Tasks")

    if not pending_tasks:
        st.info("No pending tasks. You're all caught up!")

    for task in pending_tasks:

        with st.container(border=True):

            st.markdown(f"**{task['title']}**")
            st.caption(f"Task ID: {task['id']}")

            if task["description"]:
                st.write(task["description"])

            col1, col2 = st.columns(2)

            if col1.button(
                "Mark Completed",
                key=f"complete_{task['id']}",
                use_container_width=True,
            ):
                manager.complete_task(task["id"])
                st.rerun()

            if col2.button(
                "Delete",
                key=f"delete_pending_{task['id']}",
                use_container_width=True,
            ):
                manager.delete_task(task["id"])
                st.rerun()

    # Completed tasks
    with st.expander("View Completed Tasks"):

        if not completed_tasks:
            st.info("No completed tasks yet.")

        for task in completed_tasks:

            col1, col2 = st.columns([4, 1])

            col1.write(f"✅ ~~{task['title']}~~")

            if col2.button(
                "Delete",
                key=f"delete_completed_{task['id']}",
            ):
                manager.delete_task(task["id"])
                st.rerun()
