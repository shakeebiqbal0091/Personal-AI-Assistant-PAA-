import json
import sqlite3
import uuid

import streamlit as st

from app.core.agent import PersonalAssistant
from app.tools.task_manager import TaskManager
from app.database.conversation_repository import ConversationRepository
from app.database.memory_repository import (
    ALLOWED_MEMORY_CATEGORIES,
    MAX_MEMORY_CONTENT_LENGTH,
    MemoryConflictError,
    MemoryNotFoundError,
    MemoryRepository,
    MemoryRepositoryError,
)


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


def _pending_memory_proposal_from_history(history, conversation_id):
    last_user_index = next(
        (
            index
            for index in range(len(history) - 1, -1, -1)
            if history[index].get("role") == "user"
        ),
        None,
    )
    if last_user_index is None or conversation_id is None:
        return None

    tool_names = {}
    proposals = []
    for message in history[last_user_index + 1:]:
        if message.get("role") == "assistant":
            for call in message.get("tool_calls", []):
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                call_id = call.get("id")
                if (
                    isinstance(function, dict)
                    and isinstance(call_id, str)
                    and call_id
                ):
                    tool_names[call_id] = function.get("name")
            continue

        if (
            message.get("role") != "tool"
            or not isinstance(message.get("tool_call_id"), str)
            or tool_names.get(message.get("tool_call_id")) != "propose_memory"
        ):
            continue

        try:
            result = json.loads(message.get("content", ""))
        except (json.JSONDecodeError, TypeError):
            continue

        proposal = result.get("proposal") if isinstance(result, dict) else None
        if (
            not isinstance(result, dict)
            or result.get("success") is not True
            or result.get("pending_confirmation") is not True
            or not isinstance(proposal, dict)
            or set(proposal) != {"content", "category"}
        ):
            continue

        content = proposal["content"]
        category = proposal["category"]
        if (
            not isinstance(content, str)
            or not content.strip()
            or content != content.strip()
            or len(content) > MAX_MEMORY_CONTENT_LENGTH
            or (
                category is not None
                and (
                    not isinstance(category, str)
                    or category not in ALLOWED_MEMORY_CATEGORIES
                )
            )
        ):
            continue

        proposals.append(
            {
                "operation_id": uuid.uuid4().hex,
                "conversation_id": conversation_id,
                "content": content,
                "category": category,
            }
        )

    if len(proposals) != 1:
        return None
    return proposals[0]


def _clear_pending_memory_proposal():
    st.session_state.pending_memory_proposal = None


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

if "memory_repository" not in st.session_state:
    st.session_state.memory_repository = MemoryRepository()

if "pending_memory_deletion" not in st.session_state:
    st.session_state.pending_memory_deletion = None

if "pending_memory_proposal" not in st.session_state:
    st.session_state.pending_memory_proposal = None

if "memory_proposal_notice" not in st.session_state:
    st.session_state.memory_proposal_notice = None


# ----------------------------------
# CONVERSATION HISTORY SIDEBAR
# ----------------------------------

with st.sidebar:
    st.header("Conversation History")

    repository = st.session_state.conversation_repository
    conversations = repository.list_conversations()

    if st.button("➕ New Conversation", use_container_width=True):
        _clear_pending_deletions()
        _clear_pending_memory_proposal()
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
            _clear_pending_memory_proposal()
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
        _clear_pending_memory_proposal()
        repository.delete_conversation(current_id)

        st.session_state.assistant = PersonalAssistant(
            conversation_repository=repository
        )
        st.session_state.messages = []
        st.rerun()

    st.divider()

    if st.button("Clear Current Conversation", use_container_width=True):
        _clear_pending_deletions()
        _clear_pending_memory_proposal()
        st.session_state.assistant.reset_conversation()
        st.session_state.messages = []
        st.rerun()


# ----------------------------------
# APPLICATION TABS
# ----------------------------------

assistant_tab, tasks_tab, memories_tab = st.tabs(
    ["💬 Chat Assistant", "📋 My Tasks", "🧠 Personal Memories"]
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
        _clear_pending_memory_proposal()
        st.session_state.memory_proposal_notice = None
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
            if chat_succeeded:
                st.session_state.pending_memory_proposal = (
                    _pending_memory_proposal_from_history(
                        st.session_state.assistant.conversation_history,
                        st.session_state.assistant.conversation_id,
                    )
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

    pending_memory_proposal = st.session_state.pending_memory_proposal
    if (
        pending_memory_proposal is not None
        and pending_memory_proposal["conversation_id"]
        != assistant_conversation_id
    ):
        _clear_pending_memory_proposal()
        pending_memory_proposal = None

    if pending_memory_proposal is not None:
        st.warning(
            "Review this exact proposal. Confirm Save will add it to "
            "Personal Memories; nothing has been saved yet."
        )
        st.write(pending_memory_proposal["content"])
        st.caption(
            "Category: "
            f"{pending_memory_proposal['category'] or 'Uncategorized'}"
        )
        st.caption(
            "Do not save passwords, API keys, financial credentials, "
            "or other secrets."
        )
        confirm_column, cancel_column = st.columns(2)
        operation_id = pending_memory_proposal["operation_id"]

        if confirm_column.button(
            "Confirm Save",
            key=f"confirm_save_memory_{operation_id}",
        ):
            current_proposal = st.session_state.pending_memory_proposal
            if (
                current_proposal is None
                or current_proposal["operation_id"] != operation_id
                or current_proposal["conversation_id"]
                != st.session_state.assistant.conversation_id
            ):
                st.session_state.memory_proposal_notice = {
                    "kind": "error",
                    "message": (
                        "This proposal is no longer current. No memory "
                        "was saved."
                    ),
                }
            else:
                st.session_state.pending_memory_proposal = None
                try:
                    memory_id, created = (
                        st.session_state.memory_repository
                        .create_memory_with_status(
                            current_proposal["content"],
                            current_proposal["category"],
                        )
                    )
                    if created:
                        st.session_state.memory_proposal_notice = {
                            "kind": "success",
                            "message": (
                                f"Saved memory #{memory_id} to Personal "
                                "Memories."
                            ),
                        }
                    else:
                        st.session_state.memory_proposal_notice = {
                            "kind": "info",
                            "message": (
                                f"An identical memory already exists as "
                                f"#{memory_id}; no memory was changed."
                            ),
                        }
                except MemoryRepositoryError as error:
                    st.session_state.memory_proposal_notice = {
                        "kind": "error",
                        "message": (
                            f"Could not save the proposed memory: {error}"
                        ),
                    }
                except sqlite3.Error as error:
                    st.session_state.memory_proposal_notice = {
                        "kind": "error",
                        "message": (
                            f"Could not save the proposed memory: {error}"
                        ),
                    }
            st.rerun()

        if cancel_column.button(
            "Cancel",
            key=f"cancel_save_memory_{operation_id}",
        ):
            st.session_state.pending_memory_proposal = None
            st.session_state.memory_proposal_notice = {
                "kind": "info",
                "message": "Proposal cancelled; no memory was saved.",
            }
            st.rerun()

    proposal_notice = st.session_state.pop("memory_proposal_notice", None)
    if proposal_notice is not None:
        if proposal_notice["kind"] == "error":
            st.error(proposal_notice["message"])
        elif proposal_notice["kind"] == "info":
            st.info(proposal_notice["message"])
        else:
            st.success(proposal_notice["message"])


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


# ----------------------------------
# PERSONAL MEMORY MANAGEMENT
# ----------------------------------

with memories_tab:

    memory_repository = st.session_state.memory_repository
    categories = sorted(ALLOWED_MEMORY_CATEGORIES)

    st.subheader("Personal Reference Notes")
    st.caption(
        "These notes are saved only when you explicitly add them. "
        "They are separate from chat history. When relevant, a limited "
        "selection may be included in requests sent to the configured AI "
        "provider; not all notes are sent."
    )

    notice = st.session_state.pop("memory_notice", None)
    if notice is not None:
        if notice["kind"] == "error":
            st.error(notice["message"])
        elif notice["kind"] == "info":
            st.info(notice["message"])
        else:
            st.success(notice["message"])

    with st.form("create_memory_form", clear_on_submit=True):
        memory_content = st.text_area(
            "Memory content",
            key="memory_create_content",
            help="Enter a personal reference note you want to keep.",
        )
        memory_category = st.selectbox(
            "Category",
            ["No category"] + categories,
            key="memory_create_category",
        )
        create_memory_submitted = st.form_submit_button("Save Memory")

    if create_memory_submitted:
        try:
            existing_ids = {
                memory["id"] for memory in memory_repository.list_memories()
            }
            memory_id = memory_repository.create_memory(
                memory_content,
                None if memory_category == "No category" else memory_category,
            )
            saved_memory = memory_repository.get_memory(memory_id)
            if memory_id in existing_ids:
                st.session_state.memory_notice = {
                    "kind": "info",
                    "message": (
                        f"An identical memory already exists as "
                        f"#{memory_id}; no new record was created."
                    ),
                }
            else:
                st.session_state.memory_notice = {
                    "kind": "success",
                    "message": (
                        f"Saved memory #{memory_id}: "
                        f"{saved_memory['content']}"
                    ),
                }
            st.rerun()
        except MemoryRepositoryError as error:
            st.session_state.memory_notice = {
                "kind": "error",
                "message": str(error),
            }
            st.rerun()
        except sqlite3.Error as error:
            st.session_state.memory_notice = {
                "kind": "error",
                "message": f"Could not save memory: {error}",
            }
            st.rerun()

    memories = memory_repository.list_memories()
    st.markdown("#### Saved memories")
    if not memories:
        st.info("No personal reference notes have been saved.")
    else:
        for memory in memories:
            with st.expander(
                f"Memory #{memory['id']} — "
                f"{memory['category'] or 'Uncategorized'}"
            ):
                st.write(memory["content"])
                st.caption(
                    f"Created: {memory['created_at']} · "
                    f"Updated: {memory['updated_at']}"
                )

        st.markdown("#### Edit a memory")
        memory_ids = [memory["id"] for memory in memories]
        selected_edit_id = st.selectbox(
            "Memory to edit",
            memory_ids,
            format_func=lambda memory_id: f"Memory #{memory_id}",
            key="memory_edit_selection",
        )
        selected_memory = memory_repository.get_memory(selected_edit_id)
        if selected_memory is None:
            st.error(
                "That memory is no longer available. Refresh the selection "
                "and try again."
            )
            st.session_state.memory_edit_baseline_id = None
        else:
            baseline_id = st.session_state.get("memory_edit_baseline_id")
            if baseline_id != selected_edit_id:
                st.session_state.memory_edit_baseline_id = selected_edit_id
                st.session_state.memory_edit_baseline_updated_at = (
                    selected_memory["updated_at"]
                )

            version_key = selected_memory["updated_at"].replace(" ", "_")
            edit_content_key = (
                f"memory_edit_content_{selected_edit_id}_{version_key}"
            )
            edit_category_key = (
                f"memory_edit_category_{selected_edit_id}_{version_key}"
            )
            current_category = (
                selected_memory["category"] or "No category"
            )
            edit_categories = ["No category"] + categories

            with st.form("edit_memory_form"):
                edited_content = st.text_area(
                    "Content",
                    value=selected_memory["content"],
                    key=edit_content_key,
                )
                edited_category = st.selectbox(
                    "Category",
                    edit_categories,
                    index=edit_categories.index(current_category),
                    key=edit_category_key,
                )
                update_memory_submitted = st.form_submit_button(
                    "Save Changes"
                )

            if update_memory_submitted:
                baseline_updated_at = st.session_state.get(
                    "memory_edit_baseline_updated_at"
                )

                try:
                    updated_memory = memory_repository.update_memory(
                        selected_edit_id,
                        content=edited_content,
                        category=(
                            None
                            if edited_category == "No category"
                            else edited_category
                        ),
                        expected_updated_at=baseline_updated_at,
                    )
                    st.session_state.memory_edit_baseline_updated_at = (
                        updated_memory["updated_at"]
                    )
                    st.session_state.memory_notice = {
                        "kind": "success",
                        "message": f"Updated memory #{selected_edit_id}.",
                    }
                except MemoryConflictError:
                    current_memory = memory_repository.get_memory(
                        selected_edit_id
                    )
                    if current_memory is None:
                        st.session_state.memory_edit_baseline_id = None
                        st.session_state.memory_notice = {
                            "kind": "error",
                            "message": (
                                f"Memory #{selected_edit_id} no longer exists."
                            ),
                        }
                    else:
                        st.session_state.memory_edit_baseline_updated_at = (
                            current_memory["updated_at"]
                        )
                        st.session_state.memory_notice = {
                            "kind": "error",
                            "message": (
                                f"Memory #{selected_edit_id} changed while "
                                "you were editing. The current version has "
                                "been reloaded; review it before saving again."
                            ),
                        }
                except MemoryNotFoundError as error:
                    st.session_state.memory_edit_baseline_id = None
                    st.session_state.memory_notice = {
                        "kind": "error",
                        "message": str(error),
                    }
                except MemoryRepositoryError as error:
                    st.session_state.memory_notice = {
                        "kind": "error",
                        "message": str(error),
                    }
                except sqlite3.Error as error:
                    st.session_state.memory_notice = {
                        "kind": "error",
                        "message": (
                            f"Could not update memory "
                            f"#{selected_edit_id}: {error}"
                        ),
                    }
                st.rerun()

        st.markdown("#### Delete a memory")
        selected_delete_id = st.selectbox(
            "Memory to delete",
            memory_ids,
            format_func=lambda memory_id: f"Memory #{memory_id}",
            key="memory_delete_selection",
        )
        if st.button("Request Memory Deletion", key="request_memory_delete"):
            memory_to_delete = memory_repository.get_memory(
                selected_delete_id
            )
            if memory_to_delete is None:
                st.session_state.memory_notice = {
                    "kind": "error",
                    "message": (
                        f"Memory #{selected_delete_id} no longer exists."
                    ),
                }
            else:
                st.session_state.pending_memory_deletion = {
                    "id": selected_delete_id,
                    "content": memory_to_delete["content"],
                    "category": memory_to_delete["category"],
                    "updated_at": memory_to_delete["updated_at"],
                }
            st.rerun()

        pending_memory = st.session_state.pending_memory_deletion
        if pending_memory is not None:
            current_pending_memory = memory_repository.get_memory(
                pending_memory["id"]
            )
            if current_pending_memory is None:
                st.session_state.pending_memory_deletion = None
                st.error(
                    f"Memory #{pending_memory['id']} no longer exists."
                )
            elif any(
                current_pending_memory[field] != pending_memory[field]
                for field in ("content", "category", "updated_at")
            ):
                st.session_state.pending_memory_deletion = None
                st.error(
                    f"Memory #{pending_memory['id']} changed after the "
                    "deletion request. Nothing was deleted; request deletion "
                    "again if appropriate."
                )
            else:
                st.warning(
                    f"Confirm deletion of memory #{pending_memory['id']}? "
                    f"{pending_memory['content']}"
                )
                confirm_column, cancel_column = st.columns(2)
                if confirm_column.button(
                    "Confirm Memory Deletion",
                    key="confirm_memory_deletion",
                ):
                    try:
                        memory_repository.delete_memory_if_unchanged(
                            pending_memory["id"],
                            expected_content=pending_memory["content"],
                            expected_category=pending_memory["category"],
                            expected_updated_at=pending_memory["updated_at"],
                        )
                        st.session_state.pending_memory_deletion = None
                        st.session_state.memory_notice = {
                            "kind": "success",
                            "message": f"Deleted memory #{pending_memory['id']}.",
                        }
                    except MemoryConflictError:
                        st.session_state.pending_memory_deletion = None
                        st.session_state.memory_notice = {
                            "kind": "error",
                            "message": (
                                f"Memory #{pending_memory['id']} changed "
                                "before deletion. Nothing was deleted; the "
                                "current record has been reloaded."
                            ),
                        }
                    except MemoryNotFoundError as error:
                        st.session_state.pending_memory_deletion = None
                        st.session_state.memory_notice = {
                            "kind": "error",
                            "message": f"{error} Nothing was deleted.",
                        }
                    except (MemoryRepositoryError, sqlite3.Error) as error:
                        st.session_state.memory_notice = {
                            "kind": "error",
                            "message": (
                                f"Could not delete memory "
                                f"#{pending_memory['id']}: {error}"
                            ),
                        }
                    st.rerun()

                if cancel_column.button(
                    "Cancel Memory Deletion",
                    key="cancel_memory_deletion",
                ):
                    st.session_state.pending_memory_deletion = None
                    st.rerun()
