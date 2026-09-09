# Architecture Guide

## System Design

### Overview

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                    User/Administrator                       │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
            ┌──────────────────────────────┐
            │   Frontend (React/TypeScript) │
            │   - Dashboard                  │
            │   - Batch Controls             │
            │   - Real-time Monitoring       │
            └──────────┬───────────────────┘
                       │
                       │ HTTPS
                       │
                       ▼
        ┌──────────────────────────────────┐
        │    FastAPI Backend API           │
        │  - Authentication                 │
        │  - Batch Management               │
        │  - Job Orchestration              │
        │  - SSE Event Streaming            │
        │  - Health Monitoring              │
        └──────────┬───────────────────────┘
                   │
        ┌──────────┴──────────┬──────────────┐
        │                     │              │
        ▼                     ▼              ▼
    PostgreSQL           Redis Queue    Google Sheets
    (Persistent)         (Job Queue)     (Reporting)
        │                     │
        │                     │
        └──────────┬──────────┘
                   │
                   ▼
            ┌─────────────────────────┐
            │   Worker Pool           │
            │ - Job Claiming          │
            │ - Playwright Automation │
            │ - Error Handling        │
            │ - Results Reporting     │
            └─────────────────────────┘
```

## Layer Architecture

### 1. Presentation Layer (Frontend)

**Responsibility**: User interface and interaction

**Components**:
- React application (TypeScript)
- Real-time SSE connection
- Batch creation & control
- Progress visualization
- Error display

**Technology**:
- React 18
- TypeScript
- Vite (build tool)
- Axios (HTTP client)
- EventSource (SSE)

### 2. API Layer (Backend)

**Responsibility**: Request handling and business logic coordination

**Components**:
- FastAPI web framework
- Endpoint routers (batches, health, events)
- Authentication middleware
- CORS middleware
- Request validation

**Code Organization**:
```
backend/app/
├── main.py              # FastAPI app creation
├── config.py            # Settings management
├── database.py          # DB operations
├── models/              # Pydantic models
├── api/                 # Endpoint routers
│   ├── batches.py      # Batch endpoints
│   ├── health.py       # Health checks
│   └── events.py       # SSE streaming
└── services/            # Business logic
    ├── batch_service.py
    └── event_service.py
```

**Request Flow**:
```
HTTP Request
    ↓
CORS Middleware
    ↓
Authentication Middleware
    ↓
Router (batches.py, health.py, etc.)
    ↓
Validation (Pydantic)
    ↓
Service Layer
    ↓
Database/Queue
    ↓
Response
```

### 3. Data Layer (Persistence)

**Responsibility**: Data storage and retrieval

**Components**:
- PostgreSQL database
- Redis cache/queue
- Database migrations (Alembic)
- ORM (SQLAlchemy)

**Database Schema**:

```sql
-- Batches
CREATE TABLE batches (
    id UUID PRIMARY KEY,
    referral VARCHAR NOT NULL,
    target INTEGER,
    successful INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    status VARCHAR,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Jobs for batches
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    batch_id UUID REFERENCES batches(id),
    status VARCHAR,
    worker_id VARCHAR,
    started_at TIMESTAMP,
    heartbeat_at TIMESTAMP,
    acknowledged_at TIMESTAMP
);

-- Authorized identities
CREATE TABLE authorized_test_identities (
    id UUID PRIMARY KEY,
    identifier VARCHAR UNIQUE NOT NULL,
    status VARCHAR,
    created_at TIMESTAMP,
    used_at TIMESTAMP,
    batch_id UUID REFERENCES batches(id)
);

-- Attempt tracking
CREATE TABLE attempts (
    id UUID PRIMARY KEY,
    job_id UUID REFERENCES jobs(id),
    status VARCHAR,
    error TEXT,
    attempt_number INTEGER,
    created_at TIMESTAMP
);

-- Event log
CREATE TABLE events (
    id UUID PRIMARY KEY,
    batch_id UUID REFERENCES batches(id),
    event_type VARCHAR,
    data JSONB,
    created_at TIMESTAMP
);
```

**Redis Keys**:
```
job_queue                  # Job queue
batch:{batch_id}:events   # Event stream
batch:{batch_id}:status   # Current status cache
worker:{worker_id}:heart beat # Worker heartbeat
```

### 4. Processing Layer (Worker)

**Responsibility**: Background job processing

**Components**:
- Worker process
- Job claiming mechanism
- Playwright automation
- Result reporting
- Heartbeat mechanism

**Worker Flow**:
```
Worker Start
    ↓
Connect to Redis & Database
    ↓
Loop:
  ├─ Get job from queue
  ├─ Claim identity
  ├─ Send heartbeat
  ├─ Execute automation
  ├─ Handle errors
  ├─ Report results
  └─ Acknowledge job
```

**Error Handling**:
```
Execute Task
    ↓
Success? → Report success
    ↓ No
Classification:
  ├─ NETWORK_ERROR → Retry
  ├─ TIMEOUT → Retry
  ├─ VALIDATION_ERROR → Don't retry
  ├─ AUTH_ERROR → Don't retry
  └─ UNKNOWN_ERROR → Log & Don't retry
```

## Data Flow

### Batch Creation

```
User Input
    ↓
Frontend: POST /batches
    ↓
Backend: Validate referral
    ↓
Create batch record (status: CREATED)
    ↓
Return batch to frontend
    ↓
Frontend: Displays batch
```

### Batch Processing

```
User: Click "START"
    ↓
Frontend: POST /batches/{id}/start
    ↓
Backend: Validate state transition
    ↓
Update status (CREATED → QUEUED → RUNNING)
    ↓
Add job to Redis queue
    ↓
Return to frontend
    ↓
Worker: Polls queue
    ↓
Claims job (atomically)
    ↓
Processes work
    ↓
Sends heartbeat every N seconds
    ↓
Reports results
    ↓
Acknowledges job
    ↓
Publishes event via Redis Pub/Sub
    ↓
Backend: Receives event
    ↓
Backend: Streams to frontend via SSE
    ↓
Frontend: Updates UI in real-time
```

### Error & Recovery

```
Worker Processing
    ↓
Task fails
    ↓
Log error with context (batch_id, worker_id, etc.)
    ↓
Classify error type
    ↓
Retry? 
  ├─ Yes: Update attempt, wait backoff, retry
  └─ No: Mark failed, continue with next
    ↓
All retries exhausted
    ↓
Report final status
    ↓
Publish event
    ↓
Frontend receives update
```

### Crash Recovery

```
Worker Dies
    ↓
Heartbeat stops
    ↓
Backend monitoring: No heartbeat for 30s
    ↓
Recovery thread: Mark job ABANDONED
    ↓
Reset job status to QUEUED
    ↓
Place back in Redis queue
    ↓
Next healthy worker: Claims job
    ↓
Continues processing
```

## Scaling Considerations

### Single Instance (Current)
- ✅ Simple deployment
- ✅ SQLite sufficient for dev
- ❌ No high availability
- ❌ Single point of failure

### Multi-Instance (Recommended)
```
                        Load Balancer
                              │
                ┌─────────────┼─────────────┐
                │             │             │
                ▼             ▼             ▼
            Backend 1    Backend 2    Backend 3
                │             │             │
                └─────────────┼─────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
                PostgreSQL          Redis Queue
                (shared)            (shared)
```

**Requirements**:
- Shared PostgreSQL database
- Shared Redis queue
- Multiple backend instances
- Multiple worker processes
- Load balancer frontend

### Horizontal Scaling Strategy

1. **Database**: Managed PostgreSQL (Render, AWS RDS)
2. **Cache/Queue**: Managed Redis (Render, AWS ElastiCache)
3. **API**: Multiple container instances
4. **Workers**: Separate background job service, scalable
5. **Frontend**: CDN (Netlify, Vercel)

## Communication Patterns

### Synchronous
- HTTP requests (Frontend ↔ Backend)
- Database queries
- Direct API calls

### Asynchronous
- Redis Queue (Backend → Worker)
- SSE Events (Backend → Frontend)
- Redis Pub/Sub (Worker → Backend → Frontend)

### Event Flow

```
Worker completes job
    ↓
Publishes to Redis: batch:{batch_id}:update
    ↓
Backend listeners: Subscribe to channel
    ↓
Receives event
    ↓
Broadcasts to SSE subscribers
    ↓
Frontend: SSE onmessage
    ↓
Updates state
    ↓
Re-renders UI
```

## Concurrency & Locking

### Database Locks
```
Worker 1: Reserve identity
    ↓
BEGIN TRANSACTION
    ↓
SELECT FROM identities WHERE status = AVAILABLE FOR UPDATE
    ↓
Reserve (UPDATE status to RESERVED)
    ↓
COMMIT
    ↓
Worker 2: Cannot reserve same identity (locked)
```

### Job Claiming
```
SELECT * FROM jobs WHERE batch_id = ? AND status = QUEUED LIMIT 1 FOR UPDATE
    ↓
UPDATE jobs SET status = RUNNING, worker_id = ? WHERE id = ?
    ↓
COMMIT
    ↓
Only one worker succeeds
```

## Deployment Topology

### Development
```
docker compose up
├── frontend (port 5173)
├── backend (port 8000)
├── postgres (port 5432)
└── redis (port 6379)
```

### Staging
```
Render
├── Web Service: Backend
├── Background Worker: Worker
├── Managed PostgreSQL
└── Managed Redis
```

### Production
```
CDN
├── Frontend static files
│
Load Balancer
├── Backend instance 1
├── Backend instance 2
└── Backend instance 3
     │
     ├─→ Managed PostgreSQL (replicated)
     ├─→ Managed Redis (sentinel)
     └─→ Background Workers (scalable)
```

## Technology Stack

| Layer | Component | Technology |
|-------|-----------|-----------|
| Frontend | Web Framework | React 18 |
| Frontend | Language | TypeScript |
| Frontend | Build | Vite |
| Frontend | HTTP | Axios |
| Frontend | Real-time | SSE/EventSource |
| Backend | Framework | FastAPI |
| Backend | Language | Python 3.10+ |
| Backend | ORM | SQLAlchemy |
| Backend | Validation | Pydantic |
| Backend | Server | Uvicorn |
| Database | Primary | PostgreSQL 12+ |
| Database | Cache | Redis 6+ |
| Database | Migrations | Alembic |
| Queue | System | Redis Queues |
| Automation | Browser | Playwright |
| Testing | Framework | Pytest |
| CI/CD | Platform | GitHub Actions |
| Deployment | Container | Docker |
| Deployment | Orchestration | Docker Compose (dev) |
| Deployment | PaaS | Render / AWS |

---

See [README.md](README.md) for overview and [DEPLOYMENT.md](DEPLOYMENT.md) for deployment details.
