# NovaBot frontend

The frontend is a React and TypeScript single-page application for NovaBot
customer-support chatbot. It provides customer authentication, conversational
chat, cited answers, conversation history, and an administrator knowledge-base
management interface.

## Features

- Customer registration, login, logout, and session restoration.
- Short-lived access tokens with rotated refresh tokens.
- Automatic token refresh and session-expiry handling.
- Protected customer and administrator routes.
- Responsive chat interface with:
  - New and existing conversations.
  - Conversation history and deletion.
  - Markdown-rendered assistant responses.
  - Suggested starter questions.
  - Citation buttons with document, version, page, and snippet details.
  - Cached-answer indicators and human-agent escalation notices.
  - Message length validation and loading/error states.
- Administrator document management:
  - Upload PDF, DOCX, TXT, and Markdown files.
  - Drag-and-drop upload with progress feedback.
  - Optional titles and expiration dates.
  - Document replacement/versioning.
  - Status filtering and pagination.
  - Document detail inspection.
  - Approve, archive, set/clear expiration, and delete actions.
  - Knowledge-base version display.
  - Processing-status polling and completion notifications.
- Shared API error handling, toast notifications, loading indicators, and
  responsive styling.

## Tech stack

- React 19 and TypeScript.
- Vite.
- React Router.
- TanStack React Query.
- Axios.
- React Hook Form and Zod.
- React Markdown.
- Tailwind CSS.
- Vitest and Testing Library.

## Prerequisites

- Node.js compatible with the versions in `package.json`.
- pnpm.
- A running backend API. See the [project README](../README.md) for the full
  stack setup.

## Configuration

Copy `.env.example` to `.env` and set the API URL:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

The backend must include the frontend origin in its
`CORS_ALLOWED_ORIGINS` configuration.

## Run locally

From this directory:

```powershell
pnpm install
Copy-Item .env.example .env
pnpm dev
```

The Vite development server runs at
[`http://localhost:3000`](http://localhost:3000).

## Available scripts

| Command | Description |
|---|---|
| `pnpm dev` | Start the Vite development server |
| `pnpm build` | Create a production build |
| `pnpm preview` | Preview the production build locally |
| `pnpm test` | Run the Vitest test suite |
| `pnpm run lint` | Run ESLint |

Run the frontend checks before opening a pull request:

```powershell
pnpm test
pnpm run lint
pnpm run build
```

## Application routes

| Route | Access | Purpose |
|---|---|---|
| `/login` | Public | Sign in |
| `/register` | Public | Create a customer account |
| `/chat` | Authenticated users | Ask questions and manage conversations |
| `/admin/documents` | Administrators | Manage tenant knowledge-base documents |

## Project structure

```text
src/
├── api/          API clients and shared response types
├── auth/         Authentication context and route guards
├── components/   Shared layout and UI components
├── pages/        Login, registration, chat, and document-management pages
├── lib/          Formatting and utility functions
└── test/         Test setup
```

Refresh tokens are stored in browser local storage because the API returns
them as JSON; access tokens remain in memory. Refresh requests are serialized
so rotated refresh tokens are not consumed concurrently.
