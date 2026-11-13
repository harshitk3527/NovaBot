# Presidio Support Chatbot Backend

## Setup

Python 3.11 is recommended. Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Set `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, and `OPENAI_API_KEY` in `.env`.
Security-related settings include `MAX_MESSAGE_LENGTH`, `MAX_OUTPUT_LENGTH`,
`CORS_ALLOWED_ORIGINS`, `MAX_REQUEST_SIZE_BYTES`, `CHAT_RATE_LIMIT_PER_MINUTE`,
`LOGIN_RATE_LIMIT_PER_MINUTE`, `DAILY_TOKEN_BUDGET`, `LOGIN_FAILURE_LIMIT`, and
`LOGIN_LOCKOUT_SECONDS`.

Start infrastructure and apply migrations:

```powershell
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload
```

Run the test suite:

```powershell
pytest -q
```

## Security checklist

- Keep `.env` out of source control and rotate any exposed API key.
- Use a long random `JWT_SECRET` and HTTPS in production.
- Restrict `CORS_ALLOWED_ORIGINS` to trusted frontends.
- Keep Redis and Postgres on private networks with authentication enabled.
- Review documents flagged with `needs_review` before approving them.
- Monitor audit logs for blocked prompts, login failures, rate limits, and admin actions.
- Do not grant the LLM tools or database credentials.
