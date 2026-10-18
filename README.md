# AI Customer Support & Ticketing Platform

A full-stack customer support and ticketing platform. This repository currently contains the initial backend and frontend scaffolds; product features are planned for later development.

## Requirements

- Python 3.12 or later (the current local environment uses Python 3.15)
- Node.js 22.12 or later and npm
- PostgreSQL only when database-backed features are introduced

## Backend development

From the project root in PowerShell:

```powershell
Set-Location .\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

The health endpoint is `http://127.0.0.1:8000/health`; interactive API documentation is at `http://127.0.0.1:8000/docs`.

## Frontend development

In a separate PowerShell terminal:

```powershell
Set-Location .\frontend
npm run dev
```

Vite prints the local URL when it starts. Frontend linting and production build commands are `npm run lint` and `npm run build`.

## Configuration and security

Copy `backend/.env.example` to `backend/.env` when local configuration is needed. Replace placeholders locally and never commit `.env` or production credentials. PostgreSQL is not needed to start either scaffold. No database tables or migrations are created by setup.

## Project documentation

See [docs/architecture.md](docs/architecture.md) for the initial module boundaries and future extension points.
