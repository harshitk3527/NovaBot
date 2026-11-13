# Presidio Support frontend

React + TypeScript frontend for the Presidio customer-support API.

## Run locally

```powershell
pnpm install
Copy-Item .env.example .env
pnpm dev
```

The Vite server runs at `http://localhost:3000`. Set
`VITE_API_BASE_URL=http://localhost:8000` (or your deployed API URL) in `.env`.
The backend must allow the frontend origin through its CORS configuration.

## Verify

```powershell
pnpm test
pnpm run lint
pnpm run build
```

Refresh tokens are kept in local storage because the API returns them as JSON;
access tokens remain in memory. The API client serializes refresh requests so
rotated refresh tokens are not consumed concurrently.
