# Deployment Guide

## Current Architecture

The backend runs a mock worker internally as a background thread. This works well for local development and single-instance deployments. The system uses SQLite for persistence and an in-memory queue for job management.

```
Frontend (React)
      ↓
Backend (FastAPI)
   ├── API endpoints
   └── Worker thread
      ↓
   SQLite + In-memory queue
```

## Local Development with Docker

Build and run the containerized stack:

```bash
docker compose up --build
```

Open `http://localhost:5173`. The frontend connects to the backend via the `VITE_API_URL` build argument configured in `docker-compose.yml`.

**Environment:**
- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Health check: `http://localhost:8000/health`
- Readiness check: `http://localhost:8000/ready`
- Database: SQLite at `data/signup_automation.db`

## Frontend Deployment (Netlify)

1. Set the publish directory to `frontend/dist`
2. Build command: `npm run build`
3. Environment variable:
   ```
   VITE_API_URL=https://YOUR-RENDER-BACKEND.onrender.com
   ```

## Backend Deployment (Render)

### Step 1: Create a Web Service

1. Connect your repository to Render
2. Create a new Web Service from this repository
3. Enable Docker
4. Use `backend/Dockerfile` as the Dockerfile path
5. Set start command: `uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`

### Step 2: Environment Variables

Set these environment variables in Render:

```
FRONTEND_ORIGIN=https://YOUR-NETLIFY-SITE.netlify.app
GOOGLE_SHEETS_ID=your-spreadsheet-id
GOOGLE_SHEETS_WORKSHEET=Results
GOOGLE_SERVICE_ACCOUNT_JSON=/etc/secrets/google-service-account.json
WORKER_ID=render-worker-1
```

Optional (for additional CORS origins):
```
ADDITIONAL_CORS_ORIGINS=https://another-origin.com
```

Logging levels:
```
LOG_LEVEL=INFO
```

### Step 3: Google Sheets Setup

1. Upload the Google service-account JSON as a Render secret file
2. Path: `/etc/secrets/google-service-account.json`
3. Share the target spreadsheet with the service-account email

### Step 4: Persistent Storage (Important)

The current implementation uses SQLite. To persist batch history across service restarts:

1. In Render dashboard, attach a persistent disk to your Web Service
2. Mount path: `/app/data`
3. Minimum recommended: 1GB

Without persistent storage, the database is reset on each deployment.

## Production Considerations

### Current Limitations (for reference, see tasks.txt for recommendations)

1. **Single Instance Only**: SQLite and in-memory queue don't support multiple backend instances
2. **No Queue Persistence**: Jobs in the in-memory queue are lost on restart
3. **Limited Observability**: Logging uses Python's standard logging module

### Recommended Improvements (Phases 2-5)

**Phase 2 - Database**: Migrate from SQLite to PostgreSQL for better scalability and data durability.

**Phase 3 - Architecture**: Separate the worker into a dedicated background job service:
```
Frontend → Render Web Service (FastAPI API only)
                ↓
          PostgreSQL
                ↓
          Render Background Worker (Job processing)
```

**Phase 4 - Observability**: 
- Add structured logging (structured errors, timestamps, context)
- Implement application monitoring
- Set up alerts

**Phase 5 - Frontend Enhancements**:
- Show connection status (Connected/Reconnecting/Disconnected)
- Display timestamps for batch operations
- Enhanced error messages

## Monitoring

### Health Check

```bash
curl https://YOUR-RENDER-BACKEND.onrender.com/health
```

Response:
```json
{
  "status": "healthy",
  "database": "connected"
}
```

### Readiness Check

```bash
curl https://YOUR-RENDER-BACKEND.onrender.com/ready
```

Response:
```json
{
  "status": "ready",
  "database": "ok",
  "worker": "running"
}
```

### Logs

View logs in Render dashboard under "Logs" tab. Look for:
- `Starting up Signup Automation API...`
- `Creating batch` (batch creation events)
- `Batch completed` (successful completions)
- Error messages prefixed with `ERROR`

## Troubleshooting

### Backend won't start
- Check `FRONTEND_ORIGIN` is set correctly
- Verify `GOOGLE_SERVICE_ACCOUNT_JSON` path is correct (if using Google Sheets)
- Check persistent disk is mounted if using one

### Database errors
- Ensure the persistent disk is properly mounted
- Check disk space: `df -h /app/data`

### SSE connection issues
- Frontend will attempt to reconnect every 3 seconds if connection drops
- Check browser console for network errors
- Verify `VITE_API_URL` points to correct backend

### Google Sheets integration
- Verify service account email has edit access to the spreadsheet
- Check `GOOGLE_SHEETS_ID` and `GOOGLE_SHEETS_WORKSHEET` are correct
- View logs for sheet write errors
