# Task Automation (authorized test systems only)

This project manages batches of mock or explicitly authorized test workflows. It is not a tool for creating accounts or submitting data to third-party systems.

## Architecture

React frontend -> FastAPI API -> queue/worker -> database. Local development retains SQLite and an embedded mock worker for compatibility; the Docker stack provisions PostgreSQL, Redis, and a separate worker service for the production migration.

## Run locally

1. Copy `.env.example` to `.env` and set non-default values.
2. Install development dependencies: `python -m pip install -r requirements-dev.txt`.
3. Run tests: `python -m pytest -q`.
4. Start the API: `uvicorn backend.app.main:app --reload`.
5. Start the frontend from `frontend`: `npm ci && npm run dev`.

For containers, use `docker compose up --build`. The API documentation is at `/docs`; health endpoints are `/health` and `/ready`.

## Security and deployment

Never commit `.env`, browser state, API keys, or service-account files. Enable `AUTH_REQUIRED=true`, use a strong `JWT_SECRET`, restrict `FRONTEND_ORIGIN`, put TLS in front of the API, and run the authorized adapter only against an owned test environment. See `docs/` and `DEPLOYMENT.md`.
