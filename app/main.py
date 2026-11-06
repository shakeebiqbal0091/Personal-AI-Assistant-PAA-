
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
        st.session_state.assistant = PersonalAssistant(
            conversation_repository=repository
        )
        st.session_state.messages = []
        st.rerun()

    if conversations:
        conversation_options = {
            f"{item['title']} (#{item['id']})": item["id"]
            for item in conversations
        }

        current_id = st.session_state.assistant.conversation_id
        labels = list(conversation_options.keys())

        selected_label = st.selectbox(
            "Previous Conversations",
            labels,
            index=next(
                (
                    i for i, label in enumerate(labels)
                    if conversation_options[label] == current_id
                ),
                0,
            ),
            key=f"conversation_select_{current_id}",
        )

        selected_id = conversation_options[selected_label]

        if selected_id != current_id:
            st.session_state.assistant = PersonalAssistant(
                conversation_id=selected_id,
                conversation_repository=repository,
            )

            st.session_state.messages = [
                message
                for message in st.session_state.assistant.conversation_history
                if message.get("role") in ("user", "assistant")
                and message.get("content")
            ]

            st.rerun()

        if st.button("🗑️ Delete Current Conversation"):
            repository.delete_conversation(current_id)

            st.session_state.assistant = PersonalAssistant(
                conversation_repository=repository
            )
            st.session_state.messages = []
            st.rerun()

    st.divider()

    if st.button("Clear Current Conversation", use_container_width=True):
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

    # Display conversation messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    prompt = st.chat_input("Message your Personal AI Assistant...")

    if prompt:

        # Save and display user message
        st.session_state.messages.append({
            "role": "user",
            "content": prompt,
        })

        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate assistant response
        try:
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = st.session_state.assistant.chat(prompt)

                st.markdown(response)

            # Save assistant response for the UI
            st.session_state.messages.append({
                "role": "assistant",
                "content": response,
            })

        except Exception as error:
            st.error(f"Something went wrong: {error}")


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
