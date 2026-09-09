# Task Automation System

A production-grade authorization test automation platform with real-time monitoring, persistent job tracking, and distributed worker architecture.

## 🎯 What Is This?

A system that:
- Creates batches of authorized test identities
- Distributes signup automation work across workers
- Tracks progress in real-time with Server-Sent Events (SSE)
- Manages job state, retries, and failures
- Exports results to Google Sheets

## 🏗️ Architecture

```
                    Frontend (React)
                         │
                         ▼
                    FastAPI Backend
                    ├── API Endpoints
                    ├── Authentication
                    └── SSE Live Updates
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    PostgreSQL        Redis Queue      Google Sheets
         │               │
         └───────┬───────┘
                 ▼
            Workers (Playwright)
```

### Components

**Frontend**
- React with TypeScript and Vite
- Real-time SSE batch monitoring
- Create/control batch operations
- Connection status indicator

**Backend API**
- FastAPI with structured logging
- Health (`/health`) and readiness (`/ready`) checks
- Batch CRUD operations
- Job queue management
- Authentication & authorization

**Database**
- PostgreSQL for persistent storage
- Tables: batches, jobs, identities, attempts, events
- Alembic migrations

**Job Queue**
- Redis for distributed job coordination
- Persistent queue across restarts
- Worker heartbeat monitoring

**Workers**
- Distributed Playwright automation
- Graceful shutdown
- Heartbeat-based crash recovery
- Structured error logging

## 📋 Requirements

- Python 3.10+
- Node.js 18+
- PostgreSQL 12+
- Redis 6+
- Docker & Docker Compose

## 🚀 Quick Start

### Development (SQLite)

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
npm --prefix frontend install

# Run locally
docker compose up --build

# Access:
# Frontend: http://localhost:5173
# Backend:  http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Production (PostgreSQL + Redis)

```bash
# Set environment variables
export DATABASE_URL=postgresql://user:pass@host/db
export REDIS_URL=redis://host:6379

# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start API
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# Start worker
python -m worker.worker

# Build and serve frontend
npm --prefix frontend run build
```

## 📁 Project Structure

```
task-automation/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          # FastAPI app entry point
│   │   ├── config.py        # Settings management
│   │   ├── database.py      # DB connection & operations
│   │   ├── models/
│   │   │   └── models.py    # Pydantic & SQLAlchemy models
│   │   ├── api/
│   │   │   ├── batches.py   # Batch endpoints
│   │   │   ├── health.py    # Health check endpoints
│   │   │   └── events.py    # SSE event streaming
│   │   └── services/
│   │       ├── batch_service.py
│   │       └── event_service.py
│   └── Dockerfile
│
├── worker/
│   ├── worker.py            # Worker entry point
│   ├── automation/
│   │   ├── base.py          # Base adapter
│   │   ├── mock_adapter.py  # Mock implementation
│   │   └── playwright_adapter.py
│   ├── generators/
│   │   ├── identity_generator.py
│   │   └── phone_generator.py
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── services/
│   │   └── components/
│   ├── package.json
│   └── Dockerfile
│
├── alembic/              # Database migrations
│   ├── versions/
│   └── env.py
│
├── tests/
│   ├── test_api.py
│   ├── test_worker.py
│   ├── test_database.py
│   └── conftest.py
│
├── .github/
│   └── workflows/
│       ├── test.yml      # Run tests on push
│       ├── lint.yml      # Code quality checks
│       └── deploy.yml    # Deploy to production
│
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
├── README.md
└── DEPLOYMENT.md
```

## 🔧 Configuration

All settings via environment variables in `.env`:

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost/db

# API
FRONTEND_ORIGIN=http://localhost:5173

# Worker
MAX_WORKERS=2
WORKER_LEASE_SECONDS=30

# Batch Processing
TARGET_BATCH_SIZE=1000
MAX_SIGNUP_RETRIES=3

# Security
JWT_SECRET=your-secret-key
ENVIRONMENT=development

# Google Sheets
GOOGLE_SHEETS_ID=spreadsheet-id
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/key.json
```

See `.env.example` for all options.

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=backend --cov=worker

# Run specific test
pytest tests/test_api.py::test_batch_lifecycle

# Run with output
pytest -v -s

# Frontend tests (when configured)
npm --prefix frontend run test
```

## 📊 API Documentation

After starting the backend, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

```
POST   /batches              Create batch
GET    /batches/{id}         Get batch details
POST   /batches/{id}/start   Start processing
POST   /batches/{id}/pause   Pause batch
POST   /batches/{id}/resume  Resume batch
POST   /batches/{id}/stop    Stop batch
GET    /batches/{id}/events  Stream SSE events

GET    /health               Health check
GET    /ready                Readiness check
```

## 🔐 Security

- ✅ Environment-based secrets (`.env` not committed)
- ✅ JWT authentication for API endpoints
- ✅ CORS restricted to known origins
- ✅ Rate limiting on API endpoints
- ✅ Structured logging without secrets
- ✅ Input validation with Pydantic
- ✅ Secure password hashing (for future auth)

See [SECURITY.md](SECURITY.md) for detailed security practices.

## 📚 Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment guide
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design details
- **[WORKER.md](WORKER.md)** - Worker implementation guide
- **[DATABASE.md](DATABASE.md)** - Database schema & migrations
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues & solutions

## 🚢 Deployment

### Local Docker
```bash
docker compose up --build
```

### Render (PaaS)
```bash
# Backend service:
- Framework: Docker
- Dockerfile: backend/Dockerfile
- Environment: Set DATABASE_URL, REDIS_URL, etc.

# Worker background job:
- Type: Background Worker
- Dockerfile: worker/Dockerfile
- Same environment variables

# Frontend (Netlify/Vercel):
- Build: npm run build
- Publish: frontend/dist
- Env: VITE_API_URL=https://your-backend.onrender.com
```

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

## 🔄 CI/CD Pipeline

GitHub Actions workflows in `.github/workflows/`:

1. **test.yml** - Run tests on every push
2. **lint.yml** - Code quality checks (ruff, black, mypy)
3. **deploy.yml** - Deploy to staging/production

See [CI_CD.md](CI_CD.md) for setup.

## 📈 Monitoring

### Health Checks
```bash
curl http://localhost:8000/health
# {"status": "healthy", "database": "connected"}

curl http://localhost:8000/ready
# {"status": "ready", "database": "ok", "worker": "running"}
```

### Logs
- Backend logs: stdout/stderr with structured format
- Frontend errors: Browser console
- Worker logs: Worker process logs

### Metrics (future)
- Queue size
- Worker count
- Batch completion rate
- Error rate
- Processing time

## 🛠️ Development

### Adding Features

1. Create database migration (if needed):
   ```bash
   alembic revision --autogenerate -m "describe change"
   ```

2. Add API endpoint:
   ```python
   # backend/app/api/myfeature.py
   from fastapi import APIRouter
   
   router = APIRouter(prefix="/feature", tags=["feature"])
   
   @router.get("/")
   def get_feature():
       return {"feature": "works"}
   ```

3. Register router in `main.py`:
   ```python
   from backend.app.api import myfeature
   app.include_router(myfeature.router)
   ```

4. Add tests:
   ```python
   # tests/test_myfeature.py
   def test_get_feature():
       response = client.get("/feature/")
       assert response.status_code == 200
   ```

### Code Quality
```bash
# Format code
black backend/ worker/ tests/

# Lint
ruff check backend/ worker/ tests/

# Type checking
mypy backend/

# All together
black . && ruff check . && mypy backend/
```

## 🐛 Troubleshooting

**Backend won't start:**
- Check DATABASE_URL format
- Ensure PostgreSQL is running
- Check logs for specific errors

**SSE connection drops:**
- Check browser console for errors
- Verify FRONTEND_ORIGIN matches
- Check network connectivity

**Jobs not processing:**
- Verify Redis connection
- Check worker logs
- Ensure database migrations ran

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for more.

## 📝 License

[Specify your license]

## 👥 Contributing

1. Create feature branch
2. Make changes with tests
3. Run quality checks
4. Submit PR

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## 📞 Support

- Issues: GitHub Issues
- Discussions: GitHub Discussions
- Email: [contact email if applicable]

---

**Made with ❤️ for authorized test automation**
