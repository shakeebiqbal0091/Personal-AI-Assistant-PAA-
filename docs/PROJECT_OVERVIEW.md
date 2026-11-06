# Personal AI Assistant (PAA) — Project Overview

## Current application

The working application is a local, single-user Streamlit app. It provides
chat-based assistance, task creation/listing/completion, confirmation for
AI-requested task deletion, and SQLite persistence for tasks and conversation
history.

The Python application calls an external LLM provider through an
OpenAI-compatible API. Requests include the system prompt, conversation
history, and task-tool definitions; task details returned by tools can be
included in later requests. Check the configured provider's data-handling
policies before sending sensitive content.

## Components and boundaries

- `app/main.py` runs the Streamlit interface.
- `app/core/` contains the assistant, LLM client setup, configuration, and
  intent routing.
- `app/tools/` contains task operations.
- `app/database/` contains SQLite persistence.
- `data/tasks.db` is the default local database path.
- `frontend/` contains a Next.js demo that is currently disconnected from the
  Python/Streamlit application.

The current application does not expose FastAPI endpoints, implement
authentication, or provide multi-user isolation. It is intended for local,
single-user use.

## Configuration

The Python app reads `AI_API_KEY` and `AI_MODEL` from the environment (normally
the root `.env` file). `AI_BASE_URL` defaults to OpenRouter's
`https://openrouter.ai/api/v1`. Optional active settings are `APP_NAME`,
`DEBUG`, and `USER_TZ`. See the root `.env.example` for the supported variable
names. Do not store real credentials in the example file or commit `.env`.

## Development

Use the setup, startup, and test commands in the root [README](../README.md).
The Python test suite is run with `python -m pytest`; tests marked `live` are
excluded by default and may call the configured external provider.

## Possible future work

Potential future directions include integrations with email and calendars,
workflow automation, and additional assistant capabilities. These are not
currently implemented.
