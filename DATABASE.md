# Database Guide

## Database Choices

### Development: SQLite
- ✅ Zero setup
- ✅ File-based
- ✅ Good for testing
- ❌ Single writer
- ❌ No network access

### Production: PostgreSQL
- ✅ Multi-user support
- ✅ ACID compliance
- ✅ Advanced features
- ✅ Managed options (RDS, Render)
- ✅ Replication support
- ✅ Better performance at scale

## Schema

### Batches Table

Stores batch processing sessions.

```sql
CREATE TABLE batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referral VARCHAR(120) NOT NULL,
    target INTEGER NOT NULL DEFAULT 1000,
    successful INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    attempted INTEGER NOT NULL DEFAULT 0,
    retries INTEGER NOT NULL DEFAULT 0,
    status VARCHAR NOT NULL DEFAULT 'CREATED',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Indexes
CREATE INDEX idx_batches_status ON batches(status);
CREATE INDEX idx_batches_created_at ON batches(created_at DESC);
CREATE INDEX idx_batches_referral ON batches(referral);
```

**Fields**:
- `id`: Unique batch identifier (UUID)
- `referral`: Referral code from user
- `target`: Number of identities to process
- `successful`: Count of successful signups
- `failed`: Count of failed signups
- `skipped`: Count of skipped identities
- `attempted`: Total identities attempted
- `retries`: Total retry attempts
- `status`: CREATED, QUEUED, RUNNING, PAUSED, STOPPING, COMPLETED, FAILED, CANCELLED
- `created_at`: When batch was created
- `started_at`: When batch processing started
- `completed_at`: When batch finished

**Status Transitions**:
```
CREATED → QUEUED → RUNNING ─┬→ COMPLETED
                            ├→ PAUSED → RUNNING
                            └→ STOPPING → CANCELLED
```

### Jobs Table

Tracks individual job assignments to workers.

```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    status VARCHAR NOT NULL DEFAULT 'QUEUED',
    worker_id VARCHAR,
    started_at TIMESTAMP WITH TIME ZONE,
    heartbeat_at TIMESTAMP WITH TIME ZONE,
    acknowledged_at TIMESTAMP WITH TIME ZONE
);

-- Indexes
CREATE INDEX idx_jobs_batch_id ON jobs(batch_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_worker_id ON jobs(worker_id);
CREATE INDEX idx_jobs_heartbeat_at ON jobs(heartbeat_at);
```

**Fields**:
- `id`: Job identifier
- `batch_id`: Foreign key to batch
- `status`: QUEUED, RUNNING, COMPLETED, FAILED, ABANDONED, SKIPPED, CANCELLED
- `worker_id`: Which worker claimed this job
- `started_at`: When worker started processing
- `heartbeat_at`: Last time worker sent heartbeat
- `acknowledged_at`: When worker finished job

**Status Lifecycle**:
```
QUEUED → RUNNING → COMPLETED
                 → FAILED
                 → ABANDONED (if heartbeat times out)
```

### Authorized Test Identities Table

Tracks authorized identities available for testing.

```sql
CREATE TABLE authorized_test_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identifier VARCHAR NOT NULL UNIQUE,
    status VARCHAR NOT NULL DEFAULT 'AVAILABLE',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    reserved_at TIMESTAMP WITH TIME ZONE,
    used_at TIMESTAMP WITH TIME ZONE,
    batch_id UUID REFERENCES batches(id) ON DELETE SET NULL
);

-- Indexes
CREATE INDEX idx_identities_status ON authorized_test_identities(status);
CREATE INDEX idx_identities_batch_id ON authorized_test_identities(batch_id);
CREATE UNIQUE INDEX idx_identities_reserved ON authorized_test_identities(identifier) 
    WHERE status = 'RESERVED';
```

**Fields**:
- `id`: Identity record ID
- `identifier`: Email, phone, or account ID (must be UNIQUE)
- `status`: AVAILABLE, RESERVED, PROCESSING, COMPLETED, FAILED
- `created_at`: When identity was created
- `reserved_at`: When identity was reserved for use
- `used_at`: When identity was actually used
- `batch_id`: Which batch used this identity

**Status States**:
```
AVAILABLE → RESERVED → PROCESSING → COMPLETED
                                  → FAILED
```

**Example Reserve Operation**:
```python
# Atomic identity reservation
def reserve_identity(batch_id: UUID) -> Optional[Identity]:
    with db.transaction():
        identity = db.execute("""
            SELECT * FROM authorized_test_identities 
            WHERE status = 'AVAILABLE'
            LIMIT 1
            FOR UPDATE
        """).first()
        
        if identity:
            db.execute("""
                UPDATE authorized_test_identities 
                SET status = 'RESERVED', batch_id = %s, reserved_at = NOW()
                WHERE id = %s
            """, (batch_id, identity.id))
        
        return identity
```

### Attempts Table

Tracks individual signup attempts including retries.

```sql
CREATE TABLE attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    identity_id UUID NOT NULL REFERENCES authorized_test_identities(id),
    status VARCHAR NOT NULL,
    error_type VARCHAR,
    error_message TEXT,
    attempt_number INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Indexes
CREATE INDEX idx_attempts_job_id ON attempts(job_id);
CREATE INDEX idx_attempts_identity_id ON attempts(identity_id);
CREATE INDEX idx_attempts_status ON attempts(status);
CREATE INDEX idx_attempts_error_type ON attempts(error_type);
```

**Fields**:
- `id`: Attempt ID
- `job_id`: Which job this attempt belongs to
- `identity_id`: Which identity was used
- `status`: SUCCESS, FAILURE, DUPLICATE, RETRY, TIMEOUT
- `error_type`: NETWORK_ERROR, TIMEOUT, VALIDATION_ERROR, etc.
- `error_message`: Detailed error description
- `attempt_number`: Which retry attempt (1, 2, 3...)
- `created_at`: When attempt occurred

**Usage Example**:
```sql
-- Find all failed attempts for debugging
SELECT 
    a.identity_id,
    a.error_type,
    COUNT(*) as attempt_count,
    STRING_AGG(a.error_message, '; ') as errors
FROM attempts a
WHERE a.status = 'FAILURE'
GROUP BY a.identity_id, a.error_type
ORDER BY attempt_count DESC;
```

### Events Table

Stores all significant events for auditing and replay.

```sql
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    event_type VARCHAR NOT NULL,
    event_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Indexes
CREATE INDEX idx_events_batch_id ON events(batch_id);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_created_at ON events(created_at DESC);
```

**Fields**:
- `id`: Event ID
- `batch_id`: Which batch
- `event_type`: batch_started, job_started, job_completed, job_failed, identity_used, etc.
- `event_data`: JSON object with details
- `created_at`: When event occurred

**Event Examples**:
```json
// batch_started
{
  "event_type": "batch_started",
  "batch_id": "uuid",
  "worker_id": "worker-1",
  "timestamp": "2024-01-20T10:00:00Z"
}

// job_completed
{
  "event_type": "job_completed",
  "job_id": "uuid",
  "identity_id": "uuid",
  "status": "SUCCESS",
  "attempts": 1,
  "duration_seconds": 45
}

// job_failed
{
  "event_type": "job_failed",
  "job_id": "uuid",
  "error_type": "NETWORK_ERROR",
  "error_message": "Connection timeout",
  "attempts": 3
}
```

## Migrations

Using Alembic for version-controlled schema changes.

### Initialize

```bash
alembic init alembic
```

### Create Migration

```bash
# After changing SQLAlchemy models
alembic revision --autogenerate -m "add identity status field"

# Manual migration
alembic revision -m "create indexes"
```

### Apply Migrations

```bash
# Latest
alembic upgrade head

# Specific version
alembic upgrade ae1028ead8a

# Down one
alembic downgrade -1
```

### Migration File Structure

```python
# alembic/versions/001_initial_schema.py

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'batches',
        sa.Column('id', sa.UUID, primary_key=True),
        sa.Column('referral', sa.VARCHAR(120), nullable=False),
        # ... more columns
    )
    op.create_index('idx_batches_status', 'batches', ['status'])

def downgrade():
    op.drop_index('idx_batches_status')
    op.drop_table('batches')
```

## Performance Tuning

### Indexes to Create

```sql
-- Commonly queried
CREATE INDEX idx_batches_status ON batches(status);
CREATE INDEX idx_jobs_batch_id ON jobs(batch_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_worker_id ON jobs(worker_id);
CREATE INDEX idx_identities_status ON authorized_test_identities(status);
CREATE INDEX idx_attempts_job_id ON attempts(job_id);
CREATE INDEX idx_events_batch_id ON events(batch_id);

-- Sorting
CREATE INDEX idx_batches_created_at ON batches(created_at DESC);
CREATE INDEX idx_events_created_at ON events(created_at DESC);

-- Foreign keys (usually auto-indexed)
CREATE INDEX idx_jobs_batch_id ON jobs(batch_id);
CREATE INDEX idx_attempts_identity_id ON attempts(identity_id);
```

### Query Optimization

```sql
-- BEFORE: N+1 queries
-- Problem: Loops through batches fetching jobs each time
SELECT * FROM batches;  -- 100 queries
SELECT * FROM jobs WHERE batch_id = ?;  -- 100 queries

-- AFTER: Join query
SELECT b.*, COUNT(j.id) as job_count
FROM batches b
LEFT JOIN jobs j ON b.id = j.batch_id
GROUP BY b.id;  -- 1 query

-- BEFORE: Full table scan
SELECT * FROM batches WHERE status = 'RUNNING';

-- AFTER: With index
-- (Uses index idx_batches_status)
SELECT * FROM batches WHERE status = 'RUNNING';
```

### Connection Pooling

```python
from sqlalchemy import create_engine

engine = create_engine(
    DATABASE_URL,
    pool_size=20,              # Max concurrent connections
    max_overflow=40,           # Additional overflow connections
    pool_recycle=3600,         # Recycle connections after 1 hour
    echo=False                 # Set to True for SQL logging
)
```

## Backup & Recovery

### Backup

```bash
# PostgreSQL full backup
pg_dump signup_automation > backup.sql

# Compressed backup
pg_dump signup_automation | gzip > backup.sql.gz

# With Render
# Auto-backups configured in dashboard
# Manual: Click "Back up now"
```

### Restore

```bash
# From file
psql signup_automation < backup.sql

# From compressed
gunzip < backup.sql.gz | psql signup_automation

# Verify
psql signup_automation -c "SELECT COUNT(*) FROM batches;"
```

### Point-in-Time Recovery

```bash
# PostgreSQL WAL archiving
# Configure in postgresql.conf
wal_level = replica
archive_mode = on
archive_command = 'cp %p /backup/wal_archive/%f'

# Restore to specific time
pg_basebackup -D /var/lib/postgresql/restore
# Then restore WALs up to timestamp
```

## Monitoring

### Health Checks

```sql
-- Connections
SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;

-- Slow queries
SELECT mean_exec_time, query FROM pg_stat_statements 
ORDER BY mean_exec_time DESC LIMIT 10;

-- Table sizes
SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelname) DESC;
```

### Connection Monitoring

```python
from sqlalchemy import event
from sqlalchemy.pool import Pool

@event.listens_for(Pool, "connect")
def receive_connect(dbapi_conn, connection_record):
    logger.debug(f"Connection acquired: {id(dbapi_conn)}")

@event.listens_for(Pool, "close")
def receive_close(dbapi_conn, connection_record):
    logger.debug(f"Connection returned: {id(dbapi_conn)}")

@event.listens_for(Pool, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    logger.debug(f"Connection checked out: {id(dbapi_conn)}")
```

## Best Practices

1. **Always use transactions**: Ensures consistency
2. **Foreign key constraints**: Prevents orphaned data
3. **Unique constraints**: Prevents duplicates
4. **Soft deletes**: Keep audit trail
5. **Timestamps**: created_at and updated_at on all tables
6. **Proper indexes**: On frequently queried columns
7. **Connection pooling**: Prevent resource exhaustion
8. **Backups**: Regular, tested, encrypted
9. **Monitor**: Watch slow queries and connections
10. **Migrations**: Version control schema changes

---

See [ARCHITECTURE.md](ARCHITECTURE.md) for system design and [DEPLOYMENT.md](DEPLOYMENT.md) for production setup.
