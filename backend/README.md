# Presidio Support Chatbot Backend

FastAPI backend for a tenant-isolated customer-support chatbot. It provides
password authentication, role-based administration, document ingestion and
versioning, pgvector retrieval, citation-checked RAG answers, conversation
memory, Redis semantic caching, prompt-injection defenses, rate limiting, and
audit logging.

## Architecture

- **API:** FastAPI with async SQLAlchemy 2.0 and Pydantic validation.
- **Database:** PostgreSQL with the `pgvector` extension.
- **Cache and abuse controls:** Redis Stack and RedisVL.
- **LLM services:** OpenAI embeddings, moderation, question rewriting, and
  structured chat responses.
- **Background work:** FastAPI background tasks for ingestion and APScheduler
  for document expiration.
- **Tenancy:** Users, conversations, documents, retrieval, and cache entries
  are tenant/owner scoped.

## Quick start

Python 3.11 is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set at least these values in `.env`:

```dotenv
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/presidio
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=replace-with-a-long-random-secret
OPENAI_API_KEY=replace-with-your-key
```

Start infrastructure, migrate, and run the API:

```powershell
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```

Interactive API documentation is available at `/docs`; the OpenAPI schema is
available at `/openapi.json`.

Run tests:

```powershell
pytest -q
```

Create the first administrator:

```powershell
python scripts/create_admin.py --email admin@example.com --password "change-this-password"
```

## Configuration

All settings are read from `.env` using `pydantic-settings`. Important values:

| Variable | Purpose | Default |
|---|---|---:|
| `DATABASE_URL` | Async PostgreSQL connection URL | local Postgres |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `JWT_SECRET` | JWT signing secret | development placeholder |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh-token lifetime | `7` |
| `OPENAI_API_KEY` | OpenAI API key | empty |
| `MAX_UPLOAD_SIZE_BYTES` | Maximum document size | 10 MiB |
| `MAX_MESSAGE_LENGTH` | Maximum chat message length | `4000` |
| `MAX_OUTPUT_LENGTH` | Maximum generated answer length | `10000` |
| `RETRIEVAL_SIMILARITY_CUTOFF` | Minimum retrieval similarity | `0.75` |
| `MEMORY_WINDOW_MESSAGES` | Messages used for follow-up rewriting | `8` |
| `CACHE_DISTANCE_THRESHOLD` | RedisVL cache distance threshold | `0.1` |
| `CACHE_TTL_SECONDS` | Semantic-cache TTL | `3600` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated CORS allowlist | `http://localhost:3000` |
| `CHAT_RATE_LIMIT_PER_MINUTE` | Per-user/IP chat limit | `20` |
| `LOGIN_RATE_LIMIT_PER_MINUTE` | Login rate limit | `5` |
| `DAILY_TOKEN_BUDGET` | Estimated daily user token budget | `100000` |
| `LOGIN_FAILURE_LIMIT` | Failed attempts before lockout | `5` |
| `LOGIN_LOCKOUT_SECONDS` | Account lockout period | `900` |
| `MODERATION_ENABLED` | Enable OpenAI moderation | `true` |
| `SCOPE_CLASSIFIER_ENABLED` | Enable support-scope classifier | `true` |

## Authentication

Protected endpoints require:

```http
Authorization: Bearer <access_token>
```

Public registration always creates a `customer`. Only an administrator can
create the first admin through the CLI. Access tokens last 15 minutes by
default; refresh tokens last 7 days and are rotated on every refresh.

## Endpoint reference

Unless stated otherwise, successful responses use JSON. UUIDs are represented
as strings and timestamps are ISO-8601 datetime strings.

### Health/root

#### `GET /`

No authentication.

Response `200`:

```json
{"message": "Presidio Support Chatbot API"}
```

### Authentication

#### `POST /auth/register`

Creates a customer.

Request:

```json
{
  "email": "customer@example.com",
  "password": "at-least-8-characters"
}
```

Response `201` (`UserResponse`):

```json
{
  "id": "uuid",
  "email": "customer@example.com",
  "role": "customer",
  "tenant_id": "uuid",
  "is_active": true
}
```

#### `POST /auth/login`

Request:

```json
{
  "email": "customer@example.com",
  "password": "your-password"
}
```

Response `200` (`TokenResponse`):

```json
{
  "access_token": "jwt",
  "refresh_token": "jwt",
  "token_type": "bearer"
}
```

#### `POST /auth/refresh`

Request:

```json
{"refresh_token": "jwt"}
```

Response `200`: the same `TokenResponse` shape. The submitted refresh token is
revoked and a replacement pair is issued.

#### `GET /auth/me`

Requires authentication. Response `200`: `UserResponse`.

#### `GET /auth/admin-test`

Requires an administrator. Response `200`:

```json
{"message": "admin access granted"}
```

### Chat

#### `POST /chat`

Requires authentication. Runs guardrails, loads/re-writes conversation history,
embeds the standalone question once, checks the semantic cache, retrieves
active tenant documents on a cache miss, generates a cited answer, and stores
both messages.

Request (`ChatRequest`):

```json
{
  "message": "What is your refund policy?",
  "conversation_id": "uuid-or-null"
}
```

`conversation_id` is optional. If omitted, a conversation is created.

Response `200` (`ChatResponse`):

```json
{
  "answer": "Refunds are available within 30 days.",
  "citations": [
    {
      "document_id": "uuid",
      "title": "Refund Policy",
      "version": "2",
      "page": 3,
      "chunk_id": "uuid",
      "snippet": "Refunds are available within 30 days."
    }
  ],
  "conversation_id": "uuid",
  "needs_human": false,
  "cached": false
}
```

Blocked, off-topic, unavailable, or unanswerable requests return a safe answer
with `needs_human: true` and are not cached.

### Conversations

All conversation endpoints require authentication and only return the current
user's conversations.

#### `GET /conversations`

Response `200`:

```json
[
  {
    "id": "uuid",
    "created_at": "2026-01-01T12:00:00Z"
  }
]
```

#### `GET /conversations/{conversation_id}/messages`

Response `200`:

```json
[
  {
    "id": "uuid",
    "role": "user",
    "content": "What is your refund policy?",
    "citations": null,
    "created_at": "2026-01-01T12:00:00Z"
  },
  {
    "id": "uuid",
    "role": "assistant",
    "content": "Refunds are available within 30 days.",
    "citations": [],
    "created_at": "2026-01-01T12:00:01Z"
  }
]
```

#### `DELETE /conversations/{conversation_id}`

Deletes the owner's conversation and messages. Response `204` with no body.

### Admin documents

Every endpoint in this section requires the `admin` role and is tenant scoped.

#### `POST /admin/documents`

Multipart form upload. Fields:

- `file`: required PDF, DOCX, TXT, or MD file.
- `title`: optional title; defaults to the filename stem.
- `expires_at`: optional ISO-8601 expiration datetime.

Response `202` (`DocumentResponse`) with initial `status: "processing"`.
Background ingestion extracts text, chunks it, generates embeddings, and
changes successful documents to `active`. Failed jobs become `failed`.

#### `GET /admin/documents`

Query parameters:

- `status`: optional `processing`, `active`, `superseded`, `expired`,
  `archived`, or `failed`.
- `page`: optional positive page number, default `1`.
- `page_size`: optional `1`–`100`, default `20`.

Response `200` (`DocumentListResponse`):

```json
{
  "items": [
    {
      "id": "uuid",
      "title": "Refund Policy",
      "version": "2",
      "status": "active",
      "content_hash": "sha256",
      "valid_from": "2026-01-01T12:00:00Z",
      "expires_at": null,
      "uploaded_by": "uuid",
      "superseded_by": null,
      "needs_review": false,
      "created_at": "2026-01-01T12:00:00Z"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

Documents marked `needs_review: true` are excluded from retrieval until
approved.

#### `GET /admin/documents/{document_id}`

Returns one tenant-scoped `DocumentResponse`.

#### `PATCH /admin/documents/{document_id}`

Request (`DocumentUpdateRequest`):

```json
{
  "status": "approve",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

`status` may be `archive` or `approve`. `expires_at` can be set or cleared
with `null`. Response `200`: updated `DocumentResponse`.

#### `DELETE /admin/documents/{document_id}`

Deletes the document and its chunks. Response `204` with no body.

#### `GET /admin/documents/version/current`

Response `200`:

```json
{"kb_version": 12}
```

The per-tenant KB version changes on upload, superseding, archive, expiration,
approval, and deletion operations where applicable. Semantic-cache lookups
require the current version.

## Response schemas

### `UserResponse`

| Field | Type |
|---|---|
| `id` | UUID |
| `email` | email string |
| `role` | `admin` or `customer` |
| `tenant_id` | UUID |
| `is_active` | boolean |

### `TokenResponse`

| Field | Type |
|---|---|
| `access_token` | string |
| `refresh_token` | string |
| `token_type` | string, normally `bearer` |

### `CitationResponse`

| Field | Type |
|---|---|
| `document_id` | UUID |
| `title` | string |
| `version` | string |
| `page` | integer or null |
| `chunk_id` | UUID |
| `snippet` | string, maximum 1000 characters |

### `DocumentResponse`

| Field | Type |
|---|---|
| `id` | UUID |
| `title` | string |
| `version` | string |
| `status` | document status enum |
| `content_hash` | string |
| `valid_from` | datetime |
| `expires_at` | datetime or null |
| `uploaded_by` | UUID |
| `superseded_by` | UUID or null |
| `needs_review` | boolean |
| `created_at` | datetime |

## Error format and status codes

Application errors use one consistent shape:

```json
{
  "error": {
    "code": "request_error",
    "message": "Human-readable, non-sensitive message"
  }
}
```

| HTTP status | Error code | Meaning |
|---:|---|---|
| `400` | `request_error` | Invalid operation, file type/content, or empty document update |
| `401` | `request_error` | Missing, invalid, expired, revoked, or inactive-user credentials |
| `403` | `request_error` | Authenticated user lacks the required admin role |
| `404` | `request_error` | Resource does not exist or is not owned by the caller |
| `409` | `request_error` | Duplicate active document or registered email conflict |
| `413` | `request_too_large` | Request or document exceeds the configured size limit |
| `422` | `validation_error` | Pydantic/path/query/form validation failed |
| `429` | `request_error` | Rate limit, login lockout, or daily token budget exceeded |
| `500` | `internal_error` | Unexpected server/provider failure; implementation details are not exposed |

Examples:

```json
{"error": {"code": "request_error", "message": "Invalid or expired credentials"}}
```

```json
{"error": {"code": "validation_error", "message": "Invalid request"}}
```

```json
{"error": {"code": "request_too_large", "message": "Request is too large"}}
```

## Security checklist

- Keep `.env` out of source control and rotate exposed API keys.
- Use a long random `JWT_SECRET` and HTTPS in production.
- Restrict `CORS_ALLOWED_ORIGINS` to trusted frontends.
- Keep PostgreSQL and Redis on private networks with authentication enabled.
- Review documents flagged with `needs_review` before approving them.
- Monitor audit logs for blocked prompts, login failures, rate limits, and admin actions.
- Do not grant the LLM tools or database credentials.
