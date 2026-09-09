# Architecture

The API owns batch state and exposes HTTP/SSE. Workers claim jobs, record heartbeats, and publish progress. PostgreSQL is the target shared store; Redis is the target queue and cross-instance event bus. SQLite plus the in-process queue is retained only for local mock development.

Run the API with `EMBEDDED_WORKER=false` when deploying the separate `worker` service.
