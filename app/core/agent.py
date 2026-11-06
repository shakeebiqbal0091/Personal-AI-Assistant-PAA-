
import json

from app.core.clock import current_time_context
from app.core.config import get_settings
from app.core.llm import create_llm_client
from app.core.intent_router import IntentRouter
from app.tools.task_manager import TaskManager
from app.database.conversation_repository import ConversationRepository


SYSTEM_PROMPT = """
You are Personal AI Assistant (PAA), an intelligent and reliable
personal assistant designed to help the user manage everyday life.

YOUR CORE RESPONSIBILITIES

1. Understand the user's intent.
2. Answer questions clearly and accurately.
3. Help organize tasks and personal activities.
4. Use available tools when an action is requested.
5. Remember relevant information from the current conversation.
6. Ask for clarification when necessary.

COMMUNICATION STYLE

- Be friendly, professional, natural, and concise.
- Use simple language.
- Structure longer answers with headings or bullet points.
- Avoid unnecessary technical explanations.
- Adapt your response to the user's level of understanding.
- Do not repeat information unnecessarily.

UNDERSTANDING USER INTENT

Identify what the user is trying to accomplish.

- If the user requests a task action but the target task cannot
  be identified from reliable context, do not call the tool.
  Ask the user for clarification instead.

Common types of requests include:

- General questions: Answer using your knowledge.
- Explanations: Explain concepts clearly.
- Task creation: Create a task using the appropriate tool.
- Task listing: Retrieve tasks using the appropriate tool.
- Task completion: Complete the requested task using its ID.
- Task deletion: Delete the requested task using its ID.
- Follow-up questions: Use relevant conversation context.

If a request is ambiguous and the ambiguity affects the action,
ask a short clarification question before acting.

TASK MANAGEMENT RULES

You have access to tools for creating, listing, completing,
and deleting tasks.

- Use the relevant tool whenever the user requests a task action.
- Do not claim that a task was created, completed, or deleted
  unless the corresponding tool confirms it.
- When listing tasks, accurately report the returned results.
- If a task ID is required and cannot be identified, ask for clarification.
- Never invent task IDs or task information.
- If a tool reports an error, explain the problem honestly.

CONVERSATION CONTEXT

- Use previous messages in the current conversation when relevant.
- Understand references such as "that task", "the previous one",
  and "what I mentioned earlier".
- Do not confuse information from different conversations.
- Do not invent personal information about the user.
- If you do not know something, say so.

ACCURACY AND RELIABILITY

- Never fabricate facts, actions, or tool results.
- Clearly distinguish facts from assumptions.
- If information is uncertain, acknowledge the uncertainty.
- Do not pretend to have access to external services or data
  unless an appropriate tool is available.
- Never claim to have performed an action that you did not perform.

DECISION MAKING

Before responding:
1. Understand the user's actual request.
2. Determine whether a tool is necessary.
3. Use the appropriate tool if an action is required.
4. Check the tool result.
5. Give the user a clear and truthful response.

CONTEXT AND AMBIGUITY HANDLING

You must interpret user requests using the current conversation history.

CONTEXT RESOLUTION

1. Identify the user's current intent.
2. Examine relevant previous user messages and assistant responses.
3. Identify referenced objects, such as tasks or conversations.
4. Resolve references such as:
   - "it"
   - "that task"
   - "the previous one"
   - "the first one"
   - "the last task"
   - "do the same"
5. If the reference clearly identifies one object, proceed.
6. If multiple objects could match, ask for clarification.

TASK REFERENCE RULES

When the user refers to a task:

- Use task IDs from actual tool results or conversation history.
- Never invent or guess a task ID.
- If the user refers to a task created earlier, use its actual ID.
- If the user refers to a task from a previous list, use the
  corresponding ID from that list.
- If the user says "the first one", use the first task from the
  most recent relevant task list.
- If the task cannot be identified reliably, ask the user.

AMBIGUITY HANDLING

User: "Delete my task."

Assistant: "Which task would you like me to delete?"

User: "Delete the Python task."

If exactly one matching task is known:
Use delete_task with its actual task ID.

If multiple Python tasks exist:
Ask which Python task the user means.

User: "Complete it."

If the immediately preceding context clearly identifies one task:
Use complete_task with that task's actual ID.

If no task is identifiable:
Ask which task should be completed.

User: "Do the same for Java."

Identify the previous action and determine whether it can
be safely repeated for Java.

If the previous action is unclear:
Ask a clarification question.

SAFETY

Deleting a task is a destructive action.

Before deleting:
- Identify the exact task.
- Verify its actual ID.
- Request deletion with the delete_task tool only when the target is clear.
- The tool only requests deletion; it does not delete the task.
- Never say deletion succeeded. The user must confirm in Streamlit first.

Never delete a task based on an assumed or invented task ID.

CLARIFICATION STYLE

Ask one short, direct question.

Do not ask for information that is already available
in the conversation.

Do not ask unnecessary clarification questions when the
intended action is clear.

Your primary goal is to make the user's everyday life easier
while remaining accurate, helpful, and trustworthy.
"""


TASK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new personal task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Task title",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional task description",
                    },
                },
                "required": ["title", "description"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List personal tasks by status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["all", "pending", "completed"],
                    },
                },
                "required": ["status"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a pending task as completed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "ID of the task",
                    },
                },
                "required": ["task_id"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": (
                "Request deletion of a personal task. The task is not deleted "
                "until the user confirms in Streamlit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "ID of the task",
                    },
                },
                "required": ["task_id"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    },
]

MAX_HISTORY_MESSAGES = 20
MAX_TOOL_ROUNDS = 5
TEMPERATURE = 0.2  # tool-calling agent: low variance in arguments

def trim_history(history: list[dict], keep: int = MAX_HISTORY_MESSAGES):
    """Keep the system message plus roughly the last `keep` messages.

    The window always starts on a user message, so an assistant tool_calls
    message is never separated from its tool results (providers reject
    orphaned tool messages with a 400).
    """
    system, rest = history[:1], history[1:]

    if len(rest) <= keep:
        return history

    window = rest[-keep:]
    start = next(
        (i for i, m in enumerate(window) if m.get("role") == "user"),
        None,
    )

    if start is None:
        # One very long tool turn filled the window: keep that whole turn.
        last_user = max(
            (i for i, m in enumerate(rest) if m.get("role") == "user"),
            default=0,
        )
        return system + rest[last_user:]

    return system + window[start:]


class PersonalAssistant:

    def __init__(
        self,
        client=None,
        task_manager=None,
        conversation_id=None,
        conversation_repository=None,
    ):
        self.settings = get_settings()
        self.client = client or create_llm_client(self.settings)
        self.task_manager = task_manager or TaskManager()
        self.conversation_repository = (
            conversation_repository or ConversationRepository()
        )

        # None until the first successful message: no empty rows in the DB.
        self.conversation_id = conversation_id

        saved_history = []

        if conversation_id is not None:
            saved_history = self.conversation_repository.get_history(
                conversation_id
            )

            if saved_history is None:
                raise ValueError("Conversation not found.")

        self.conversation_history = self._new_history(saved_history)

    # ==========================================
    # HISTORY / PROMPT HELPERS
    # ==========================================

    @staticmethod
    def _new_history(saved: list[dict]) -> list[dict]:
        """System prompt lives in memory only; any system message stored
        by older versions is dropped so prompt updates apply everywhere."""
        return [{"role": "system", "content": SYSTEM_PROMPT}] + [
            message for message in saved
            if message.get("role") != "system"
        ]

    def _messages_for_model(self) -> list[dict]:
        system = {
            "role": "system",
            "content": (
                f"{SYSTEM_PROMPT}\n"
                "CURRENT TIME\n\n"
                f"{current_time_context(self.settings.user_tz)}\n"
                'Resolve relative dates such as "today" or "tomorrow" '
                "against this."
            ),
        }

        return [system] + self.conversation_history[1:]

    def _persist(self) -> None:
        if self.conversation_id is None:
            self.conversation_id = (
                self.conversation_repository.create_conversation()
            )

        self.conversation_repository.save_history(
            self.conversation_id,
            self.conversation_history[1:],  # never store the system prompt
        )

    # ==========================================
    # STRUCTURED TOOL EXECUTION
    # ==========================================

    def _execute_tool(self, name: str, arguments: dict) -> dict:
        try:
            return IntentRouter.route(
                intent_name=name,
                arguments=arguments,
                task_manager=self.task_manager,
            )

        except ValueError as error:
            return {
                "success": False,
                "error": "invalid_arguments",
                "message": str(error),
            }

        except Exception:
            return {
                "success": False,
                "error": "execution_failed",
                "message": "The requested action could not be completed.",
            }

    # ==========================================
    # AI CHAT
    # ==========================================

    def chat(self, user_message: str) -> str:
        user_message = user_message.strip()

        if not user_message:
            raise ValueError("Message cannot be empty.")

        original_history = list(self.conversation_history)
        last_persisted_history = None
        delete_task_results = []

        self.conversation_history.append(
            {"role": "user", "content": user_message}
        )

        try:
            for _ in range(MAX_TOOL_ROUNDS):
                response = self.client.chat.completions.create(
                    model=self.settings.model,
                    messages=self._messages_for_model(),
                    tools=TASK_TOOLS,
                    tool_choice="auto",
                    temperature=TEMPERATURE,
                )

                message = response.choices[0].message
                tool_calls = getattr(message, "tool_calls", None)

                if not tool_calls:
                    assistant_message = (message.content or "").strip()

                    if not assistant_message:
                        raise RuntimeError(
                            "The AI returned an empty response."
                        )

                    if delete_task_results:
                        messages = []
                        for result in delete_task_results:
                            if result.get("pending_confirmation"):
                                task = result["task"]
                                messages.append(
                                    f"I found '{task['title']}' (ID "
                                    f"{task['id']}). Please review and confirm "
                                    "the deletion in the app. No task has been "
                                    "deleted."
                                )
                            else:
                                messages.append(
                                    result.get(
                                        "message",
                                        "The deletion request could not be "
                                        "completed.",
                                    )
                                )
                        assistant_message = " ".join(messages)
                    self.conversation_history.append(
                        {"role": "assistant", "content": assistant_message}
                    )

                    self.conversation_history = trim_history(
                        self.conversation_history
                    )
                    self._persist()

                    return assistant_message

                self.conversation_history.append(
                    {
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            call.model_dump() for call in tool_calls
                        ],
                    }
                )

                for call in tool_calls:
                    try:
                        arguments = json.loads(call.function.arguments)
                        result = self._execute_tool(
                            call.function.name,
                            arguments,
                        )

                    except (json.JSONDecodeError, TypeError):
                        result = {
                            "success": False,
                            "error": "invalid_arguments",
                            "message": "Invalid tool arguments.",
                        }

                    if call.function.name == "delete_task":
                        delete_task_results.append(result)

                    self.conversation_history.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(result),
                        }
                    )

                self._persist()
                last_persisted_history = list(self.conversation_history)

            raise RuntimeError("Maximum tool execution rounds reached.")

        except Exception:
            self.conversation_history = (
                last_persisted_history
                if last_persisted_history is not None
                else original_history
            )
            raise

    # ==========================================
    # RESET CONVERSATION
    # ==========================================

    def reset_conversation(self) -> None:
        self.conversation_history = self._new_history([])

        if self.conversation_id is not None:
            self._persist()