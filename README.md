# Personal AI Assistant (PAA)

PAA is a local, single-user personal assistant with a working Streamlit
application, an OpenAI-compatible external LLM provider, and SQLite task and
conversation storage. The Next.js frontend is currently a disconnected demo; it
does not communicate with the Python application.

## Prerequisites

- Windows with PowerShell
- Python 3.10 or later
- An API key and model ID for an OpenAI-compatible LLM provider

The default provider URL is OpenRouter (`https://openrouter.ai/api/v1`). You
can configure another compatible provider with `AI_BASE_URL`.

## Setup (PowerShell)

Run these commands from the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and replace the `AI_API_KEY` and `AI_MODEL` placeholders with your
provider credentials and selected model ID. Never commit or share the `.env`
file. If PowerShell blocks activation, use the virtual environment's Python
directly instead, for example:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use the same `.venv\Scripts\python.exe` prefix for the application and test
commands below if the virtual environment is not activated.

## Run the application

From the repository root, with the virtual environment activated:

```powershell
python -m streamlit run app/main.py
```

Streamlit prints the local URL to open in your browser. The application stores
tasks and conversation history in `data/tasks.db`.

## Run the Python tests

From the repository root:

```powershell
python -m pytest
```

The default pytest configuration excludes tests marked `live`. Live LLM tests
may contact the configured provider and can incur charges.

## Architecture and data handling

- Streamlit is the working application. The Next.js frontend under `frontend/`
  is a disconnected demo and is not connected to the Python app.
- The current application is local and single-user. It does not provide
  authentication or multi-user data isolation.
- Chat requests are sent to the configured external LLM provider through its
  OpenAI-compatible API. Requests include the system prompt, conversation
  history, and available task-tool definitions; task details returned by a
  tool may therefore be included in subsequent requests. Review the provider's
  data-handling and retention policies before sending sensitive information.
- SQLite persistence is local to this application. No FastAPI endpoints are
  currently used by the working application.
