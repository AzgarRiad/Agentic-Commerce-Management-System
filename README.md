# Agentic Commerce Management System (ACMS)

A small hobby project: a store admin dashboard plus an AI chat assistant that
can look up products and place orders. Built with FastAPI, SQLAlchemy and
plain HTML/CSS/JavaScript.

## Features

- Dashboard to manage products and orders (add, edit, delete, change order status)
- Chat assistant (`POST /chat`) that checks product prices/stock and saves orders
- Works with Groq, Gemini or OpenRouter through the OpenAI SDK
- SQLite by default, PostgreSQL optional

## Setup

1. Install [uv](https://docs.astral.sh/uv/) (Python 3.11+).
2. Install dependencies:

   ```bash
   uv sync
   ```

3. Copy `.env.example` to `.env` and add your API key:

   ```bash
   cp .env.example .env
   ```

   Set `LLM_PROVIDER` (`groq`, `gemini` or `openrouter`) and the matching key.
   `DB_URL` is optional; without it a SQLite file is created in `data/`.

## Run

```bash
uv run uvicorn app.api.webapi:app --reload --port 8000
```

- Admin dashboard: http://127.0.0.1:8000
- Messenger chat mock: http://127.0.0.1:8000/messenger
- API docs: http://127.0.0.1:8000/docs
- Chat example:

  ```bash
  curl -X POST http://127.0.0.1:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "What products do you have?"}'
  ```

The database starts empty, so add a few products in the dashboard first.

## Project structure

- `app/api/` - FastAPI routes (`webapi.py`, `dashboardapi.py`) and the chat loop (`chat.py`)
- `app/agent/` - database setup, models, and the tools the AI can call
- `acms-plain/` - dashboard frontend (served by FastAPI)
- `messanger_demo/` - Messenger-style chat mock (served at `/messenger`)
- `data/` - created at runtime (SQLite DB and chat history, not committed)

## Notes

- Chat history is stored in one shared file (`data/conversation.json`), so it is meant for a single user/demo.
- Never commit your `.env` file; it holds your API keys.
