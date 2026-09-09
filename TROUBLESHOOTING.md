# Troubleshooting Guide

## Quick Diagnostics

### Backend Won't Start

**Error**: `ModuleNotFoundError: No module named 'fastapi'`

```bash
# Solution: Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

**Error**: `FATAL: database "signup_automation" does not exist`

```bash
# Solution: Create database
createdb signup_automation
# Or if using Render, configure DATABASE_URL
export DATABASE_URL=postgresql://user:pass@localhost/db
```

**Error**: `refused to connect`

```bash
# Check PostgreSQL is running
psql -U postgres -c "\l"

# Check Redis is running
redis-cli ping

# On Docker
docker ps | grep postgres
docker ps | grep redis
```

### Frontend Won't Connect

**Error**: CORS error in browser console

```
Access-Control-Allow-Origin: header not found
```

```bash
# Solution: Set FRONTEND_ORIGIN
export FRONTEND_ORIGIN=http://localhost:5173

# Or check docker-compose.yml has FRONTEND_ORIGIN set
```

**Error**: `VITE_API_URL not defined`

```bash
# Build with API URL
VITE_API_URL=http://localhost:8000 npm run build

# Or set in .env
VITE_API_URL=http://localhost:8000
```

**Error**: SSE connection drops immediately

```
Connection closed by server
```

```bash
# Check backend is running:
curl http://localhost:8000/health

# Check frontend logs (browser console)
# Common causes:
# 1. Backend crashed
# 2. Network connectivity
# 3. VITE_API_URL points to wrong server
```

### Database Issues

**Error**: `relation "batches" does not exist`

```bash
# Solution: Run migrations
alembic upgrade head

# Or initialize manually
python -c "from backend.app.database import initialize_database; initialize_database()"
```

**Error**: `disk I/O error` or `database locked`

```bash
# SQLite issue - only one writer at a time
# Solution: Use PostgreSQL in production

# For SQLite dev, close all connections and restart:
pkill -f "pytest"
pkill -f "python.*uvicorn"
rm data/signup_automation.db
```

**Error**: `connection refused` on PostgreSQL

```bash
# Check PostgreSQL running
sudo systemctl status postgresql

# Or with Docker
docker ps | grep postgres

# Connection string format
# postgresql://user:password@host:port/database
# Example: postgresql://user:pass@localhost:5432/signup_automation
```

### Worker Issues

**Error**: Worker not processing jobs

```bash
# Check worker is running
ps aux | grep worker

# Check Redis queue
redis-cli LLEN job_queue

# Check logs
# Worker should output:
# - "Worker started"
# - "Claiming job"
# - "Processing batch"
```

**Error**: Jobs stuck in RUNNING state

```bash
# Worker crashed without acknowledging
# Solution: Restart worker (recovery kicks in after heartbeat timeout)

# Manual recovery:
python -c "
from backend.app.database import recover_abandoned_jobs
recovered = recover_abandoned_jobs()
print(f'Recovered {recovered} jobs')
"
```

**Error**: Out of memory / Too many processes

```bash
# Check browser processes (Playwright)
ps aux | grep chromium
ps aux | grep firefox

# Kill stale processes
pkill -f chromium
pkill -f firefox

# In production: Configure max workers
export MAX_WORKERS=2
```

## Detailed Diagnostics

### Health Check Workflow

```bash
# 1. API is running?
curl -v http://localhost:8000/health
# Should return: {"status": "healthy", "database": "connected"}

# 2. Readiness check
curl -v http://localhost:8000/ready
# Should return: {"status": "ready", "database": "ok", "worker": "running"}

# 3. Database connectivity
python -c "
from backend.app.database import connect
from contextlib import closing
try:
    with closing(connect()) as conn:
        conn.execute('SELECT 1')
    print('✓ Database connected')
except Exception as e:
    print(f'✗ Database error: {e}')
"

# 4. Redis connectivity
redis-cli ping
# Should return: PONG

# 5. Check logs
# Docker: docker logs <container-name>
# File: tail -f backend.log
```

### Performance Debugging

**Slow API Responses**

```bash
# Check slow queries
# PostgreSQL
psql -U user -d signup_automation -c "
SELECT mean_exec_time, query FROM pg_stat_statements 
ORDER BY mean_exec_time DESC LIMIT 10;
"

# Add indexes if needed
CREATE INDEX idx_batches_status ON batches(status);
CREATE INDEX idx_jobs_batch_id ON jobs(batch_id);
CREATE INDEX idx_jobs_status ON jobs(status);
```

**High Memory Usage**

```bash
# Check Python process memory
ps aux | grep python | head -5
# Format: USER PID %CPU %MEM VSZ RSS

# Check container memory
docker stats <container-name>

# Profile with memory_profiler
pip install memory_profiler
python -m memory_profiler backend/app/main.py
```

**Slow Worker Processing**

```bash
# Check individual job time
# In logs, look for:
# "Job {job_id} completed in {duration}s"

# Profile with cProfile
python -m cProfile -s cumulative -m worker.worker

# Check Playwright waits
# Long waits = slow selectors or network issues
```

### Debugging Batch Processing

**Batch stuck in RUNNING**

```bash
# Check database state
psql -U user -d signup_automation -c "
SELECT id, status, started_at FROM batches 
WHERE status = 'RUNNING' AND completed_at IS NULL;
"

# Check for stale jobs
SELECT job_id, status, heartbeat_at FROM jobs 
WHERE status = 'RUNNING' 
AND heartbeat_at < NOW() - interval '1 minute';

# Solution: Recover jobs
python -c "from backend.app.database import recover_abandoned_jobs; recover_abandoned_jobs()"
```

**Batch not progressing**

```bash
# Check job queue has jobs
redis-cli LLEN job_queue
redis-cli LRANGE job_queue 0 -1

# Check worker is claiming jobs
# Enable debug logging:
export LOG_LEVEL=DEBUG

# Watch logs:
tail -f backend.log | grep -E "claiming|processing"
```

**Identity duplicates**

```bash
# Check for duplicate identities
SELECT identifier, COUNT(*) FROM authorized_test_identities 
GROUP BY identifier HAVING COUNT(*) > 1;

# Fix: Reset duplicates
DELETE FROM authorized_test_identities 
WHERE id NOT IN (
    SELECT DISTINCT ON (identifier) id 
    FROM authorized_test_identities 
    ORDER BY identifier, created_at DESC
);
```

## Common Scenarios

### Scenario 1: "Batch completed but shows 0 successful"

**Cause**: Mock adapter always returns success, but not being recorded

**Check**:
```bash
# Are jobs actually created?
SELECT * FROM jobs WHERE batch_id = 'xxx';

# Are results being saved?
SELECT * FROM attempts WHERE job_id IN (...);

# Check worker logs for errors
grep -i "error\|failed" backend.log
```

**Solution**:
```bash
# Recreate batch and watch logs in real-time
tail -f backend.log &
# Then create batch via API
curl -X POST http://localhost:8000/batches \
  -H "Content-Type: application/json" \
  -d '{"referral":"DEBUG123"}'
```

### Scenario 2: "SSE connection works then drops"

**Cause**: Backend crashed, connection timeout, or error

**Check**:
```bash
# Monitor backend logs:
tail -f backend.log | grep -E "ERROR|error"

# Check if backend is still responsive:
watch -n 1 'curl -s http://localhost:8000/health'

# Check network:
netstat -tnp | grep 8000
```

**Solution**:
```bash
# If backend crashed, restart:
# Stop current process
pkill -f "uvicorn"

# Restart with logging:
PYTHONUNBUFFERED=1 python -m uvicorn backend.app.main:app --reload

# Frontend will automatically reconnect
```

### Scenario 3: "Workers consuming CPU but not progressing"

**Cause**: Stuck in loop, browser processes not closing, or infinite retry

**Check**:
```bash
# Check browser processes
ps aux | grep -E "chromium|firefox" | wc -l

# Check worker logs
grep -i "infinite\|loop\|stuck" backend.log

# Check retry attempt count
SELECT job_id, COUNT(*) as attempts FROM attempts 
GROUP BY job_id ORDER BY COUNT(*) DESC LIMIT 5;
```

**Solution**:
```bash
# Kill stale browser processes:
pkill -9 -f "chromium\|firefox"

# Increase timeout:
export WORKER_LEASE_SECONDS=60

# Reset stuck jobs:
UPDATE jobs SET status = 'ABANDONED' 
WHERE status = 'RUNNING' 
AND heartbeat_at < NOW() - interval '5 minutes';
```

### Scenario 4: "Deployment to Render fails"

**Check**:
```bash
# Render logs show what went wrong
# Common causes:

# 1. Missing environment variables
# Check Render dashboard > Environment

# 2. Database migration failed
# Try local: alembic upgrade head

# 3. Missing dependencies
# Check requirements.txt all packages

# 4. Wrong Dockerfile
# Verify backend/Dockerfile uses right entrypoint
```

**Solution**:
```bash
# Build locally first
docker build -f backend/Dockerfile -t signup-backend:test .
docker run -e DATABASE_URL=sqlite:///test.db signup-backend:test

# If it works locally, issue is with Render config
# If it fails locally, fix before pushing
```

## Monitoring Commands

### System Health

```bash
# Docker Compose stack
docker compose ps

# Logs (real-time)
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f postgres

# Resource usage
docker stats

# Specific errors
docker logs <container> | grep -i error
```

### Database Health

```bash
# PostgreSQL
psql signup_automation -c "\d"  # List tables
psql signup_automation -c "SELECT * FROM pg_stat_activity;"

# Redis
redis-cli
> INFO stats
> DBSIZE
> KEYS *
```

### Job Queue

```bash
redis-cli

# Queue size
LLEN job_queue

# Queue contents (first 10)
LRANGE job_queue 0 10

# Clear queue (danger!)
DEL job_queue

# Monitor events
PSUBSCRIBE batch:*
```

### Application Logs

```bash
# Filter by level
grep "ERROR" backend.log
grep "WARNING" backend.log
grep "INFO" backend.log

# Filter by component
grep "batch\|job\|worker" backend.log

# Timeline
grep "2024-01-20" backend.log | head -20

# Tail with search
tail -f backend.log | grep -E "ERROR|CRITICAL"
```

## Integration Testing

```bash
# Full stack health check
python tests/integration/test_health_check.py

# Batch lifecycle
python tests/integration/test_batch_lifecycle.py

# Worker processing
python tests/integration/test_worker_processing.py

# All integration tests
pytest tests/integration/ -v
```

## Getting Help

1. **Check logs first**: 90% of issues are in logs
2. **Isolate the layer**: Frontend? API? Database? Worker?
3. **Reproduce locally**: Docker compose should replicate production
4. **Check health endpoints**: `/health` and `/ready`
5. **Review recent changes**: What changed before it broke?

### Creating an Issue

Include:
- Error message (exact copy)
- Logs (relevant section)
- Steps to reproduce
- Environment (Docker? Local? Render?)
- What works / what doesn't

---

Still stuck? Check [ARCHITECTURE.md](ARCHITECTURE.md) or [DEPLOYMENT.md](DEPLOYMENT.md).
