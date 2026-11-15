# NovaBot

NovaBot is a tenant-isolated customer-support platform. It
combines a React frontend with a FastAPI backend to answer support questions
from an administrator-managed document knowledge base.

## Features

### Customer experience

- Customer registration and password authentication.
- Role-based access for customers and administrators.
- Secure access/refresh token authentication with refresh-token rotation.
- Conversation creation, history, and deletion.
- Context-aware chat follow-ups with conversation memory.
- Retrieval-augmented answers grounded in tenant-scoped documents.
- Inline citations containing document title, version, page, and snippet.
- Semantic response caching for repeated questions.
- Safe handling of blocked, off-topic, unavailable, or unanswerable requests.
- Human-agent escalation indicators.
- Responsive web UI with loading, error, and success notifications.

### Knowledge-base administration

- Upload PDF, DOCX, TXT, and Markdown documents.
- Background text extraction, chunking, and embedding generation.
- Document versioning and replacement.
- Tenant-scoped document listing with status filters and pagination.
- Document details, expiration dates, approval, archiving, and deletion.
- Review flags for documents that should not yet be used for retrieval.
- Automatic expiration of stale documents.
- Knowledge-base version tracking to invalidate stale cached answers.

### Backend reliability and security

- FastAPI with async SQLAlchemy and Pydantic validation.
- PostgreSQL with the `pgvector` extension for vector retrieval.
- Redis Stack and RedisVL for semantic caching and abuse controls.
- OpenAI embeddings, moderation, question rewriting, and structured answers.
- Prompt-injection defenses and support-scope classification.
- PII redaction, rate limiting, login lockout, and daily token budgets.
- Tenant/owner scoping for users, conversations, documents, retrieval, and
  cache entries.
- Consistent JSON errors, request-size limits, security headers, and audit
  logging.
- Automated tests for authentication, chat, documents, guardrails, caching,
  and security controls.

## Architecture

```text
React + TypeScript frontend  -- HTTP/JSON -->  FastAPI backend
                                                   |
                         +-------------------------+-------------------------+
                         |                         |                         |
                    PostgreSQL                 Redis Stack                 OpenAI
                    + pgvector                 cache/limits             LLM/embeddings
```

## Repository layout

```text
backend/       FastAPI API, database models, ingestion, RAG, and tests
frontend/      React/Vite application and frontend tests
```

## Prerequisites

- Python 3.11 recommended.
- Node.js and pnpm.
- Docker Desktop for PostgreSQL and Redis.
- An OpenAI API key for embeddings and generated answers.

## Quick start

### 1. Start backend infrastructure

From `backend`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```

Set at least these values in `backend/.env`:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/novabot
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=replace-with-a-long-random-secret
OPENAI_API_KEY=replace-with-your-key
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

The API is available at
[`http://localhost:8000`](http://localhost:8000). Interactive documentation
is available at [`http://localhost:8000/docs`](http://localhost:8000/docs).

### 2. Create an administrator

With the backend virtual environment active:

```powershell
python scripts/create_admin.py --email admin@example.com --password "change-this-password"
```

### 3. Start the frontend

From `frontend`:

```powershell
pnpm install
Copy-Item .env.example .env
pnpm dev
```

The application is available at
[`http://localhost:3000`](http://localhost:3000). The default
`VITE_API_BASE_URL` points to the local backend.

## Verification

Backend:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

Frontend:

```powershell
cd frontend
pnpm test
pnpm run lint
pnpm run build
```

## API overview

The backend exposes:

- `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, and
  `GET /auth/me` for authentication.
- `POST /chat` for grounded support answers.
- `GET /conversations`,
  `GET /conversations/{conversation_id}/messages`, and
  `DELETE /conversations/{conversation_id}` for conversation management.
- `/admin/documents` endpoints for administrator document management.
- `GET /admin/documents/version/current` for the tenant knowledge-base version.

See the [backend README](backend/README.md) for the complete endpoint
reference, response schemas, configuration table, and security checklist.
See the [frontend README](frontend/README.md) for UI routes, frontend
configuration, and development scripts.

## Security notes

- Never commit `.env` files or API keys.
- Use a long random `JWT_SECRET` and HTTPS outside local development.
- Restrict `CORS_ALLOWED_ORIGINS` to trusted frontend origins.
- Keep PostgreSQL and Redis on private, authenticated networks in production.
- Review flagged documents before approving them for retrieval.
