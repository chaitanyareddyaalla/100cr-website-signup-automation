# API

`POST /batches`, `GET /batches/{id}`, and `POST /batches/{id}/{start|pause|resume|stop}` manage batches. `GET /batches/{id}/events` streams Server-Sent Events. `GET /health` and `GET /ready` support platform checks. FastAPI publishes the interactive schema at `/docs`.

Production endpoints must use JWT authentication: ADMIN manages all operations, OPERATOR manages and monitors batches, and VIEWER has read-only access.
