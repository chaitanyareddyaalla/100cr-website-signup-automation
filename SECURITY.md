# Security Guide

## 🔐 Security Checklist

Before deployment, ensure all items are addressed:

### Secrets Management
- ✅ `.env` is in `.gitignore`
- ✅ No hardcoded passwords or API keys
- ✅ Use environment variables for all secrets
- ✅ Create `.env.example` with placeholder values
- ✅ Use Render/deployment-platform secret management

### Code Security
- ✅ Input validation with Pydantic models
- ✅ No SQL injection (use parameterized queries)
- ✅ Proper error handling without exposing internals
- ✅ No credentials in logs
- ✅ Type hints for better safety

### API Security
- ✅ CORS restricted to known origins
- ✅ Rate limiting enabled
- ✅ HTTPS enforced in production
- ✅ Authentication required for protected endpoints
- ✅ Authorization checks per endpoint

### Database Security
- ✅ Unique constraints on sensitive data
- ✅ Prepared statements for all queries
- ✅ Database user with minimal privileges
- ✅ Encrypted connections (SSL/TLS)
- ✅ Regular backups with encryption

### Deployment Security
- ✅ Secrets in platform secret management
- ✅ Not in environment variable files
- ✅ Restricted database access (firewall)
- ✅ Redis with authentication
- ✅ Regular dependency updates

## 🔑 Secret Handling

### Local Development

Create `.env` file (never commit):
```bash
# .env (DO NOT COMMIT)
DATABASE_URL=postgresql://user:pass@localhost/db
REDIS_URL=redis://localhost:6379
JWT_SECRET=dev-secret-key
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/key.json
```

Use `.env.example` for documentation:
```bash
# .env.example (COMMIT THIS)
DATABASE_URL=postgresql://user:pass@localhost/db
REDIS_URL=redis://localhost:6379
JWT_SECRET=your-secret-key-here
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/key.json
```

### Production Deployment

For Render/Vercel/similar platforms:

1. Never paste secrets into environment variable UI
2. Use platform's secret file feature:
   - Upload `service-account.json` as secret file
   - Reference path: `/etc/secrets/service-account.json`
3. Use `DATABASE_URL` from managed PostgreSQL
4. Generate strong `JWT_SECRET`:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

## 🛡️ Authentication Implementation

### JWT Token Flow

```
User Login
    ↓
Validate credentials
    ↓
Generate JWT token
    ↓
Return token to client
    ↓
Client includes in Authorization header
    ↓
Backend verifies token signature
    ↓
Grant access
```

### Protected Endpoint Example

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthCredentials

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthCredentials = Depends(security)):
    token = credentials.credentials
    # Verify JWT signature
    # Return user info or raise HTTPException
    return user

@app.post("/batches")
async def create_batch(data: ReferralRequest, user = Depends(verify_token)):
    # Only authenticated users can create batches
    return create_batch(data.referral)
```

## 🚫 Common Vulnerabilities

### SQL Injection
❌ Don't:
```python
query = f"SELECT * FROM batches WHERE id = {batch_id}"
```

✅ Do:
```python
query = "SELECT * FROM batches WHERE id = ?"
connection.execute(query, (batch_id,))
```

### Hardcoded Secrets
❌ Don't:
```python
DATABASE_URL = "postgresql://user:password@localhost/db"
JWT_SECRET = "super-secret-key-123"
```

✅ Do:
```python
DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET = os.getenv("JWT_SECRET")
```

### Exposed Errors
❌ Don't:
```python
@app.get("/batches/{id}")
def get_batch(id: str):
    try:
        return query_database(id)
    except Exception as e:
        return {"error": str(e)}  # Exposes internals!
```

✅ Do:
```python
@app.get("/batches/{id}")
def get_batch(id: str):
    try:
        return query_database(id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Batch not found")
    except Exception as e:
        logger.error(f"Error fetching batch: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")
```

### Missing Rate Limiting
❌ Don't allow unlimited requests per user

✅ Do:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/batches")
@limiter.limit("100/minute")
async def create_batch(request: Request, data: ReferralRequest):
    return create_batch(data.referral)
```

### Broad CORS
❌ Don't:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # NEVER in production!
)
```

✅ Do:
```python
allowed_origins = os.getenv("ALLOWED_ORIGINS", "").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # Specific domains only
)
```

## 📋 Security Audit

Before going live, complete this audit:

### Code Review
- [ ] No `TODO` with security implications
- [ ] All inputs validated
- [ ] All errors handled gracefully
- [ ] All secrets come from environment
- [ ] Logging doesn't expose secrets

### Dependencies
- [ ] Run `pip audit` for vulnerabilities
- [ ] Update to latest secure versions
- [ ] Remove unused dependencies
- [ ] Pin versions in production

### Infrastructure
- [ ] Database firewall rules configured
- [ ] Redis authentication enabled
- [ ] HTTPS enabled (automatic on Render)
- [ ] Secret files not in version control
- [ ] Backup encryption enabled

### Monitoring
- [ ] Logs being collected
- [ ] Alerts configured for errors
- [ ] Security-relevant events logged
- [ ] No sensitive data in logs
- [ ] Regular log review scheduled

## 🔄 Incident Response

### Data Breach
1. Stop affected service immediately
2. Rotate all compromised credentials
3. Review access logs for impact scope
4. Notify users if data was exposed
5. Update to newer credentials

### Unauthorized Access
1. Invalidate attacker's tokens
2. Reset affected user passwords
3. Review what data was accessed
4. Strengthen access controls
5. Monitor for further activity

### Service Compromise
1. Take service offline
2. Review code for backdoors
3. Rebuild from clean source
4. Redeploy with new secrets
5. Audit all recent activity

## 📚 Security Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [PostgreSQL Security](https://www.postgresql.org/docs/current/sql-syntax.html)
- [Redis Security](https://redis.io/topics/security)

## 🔗 Related Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment security
- [README.md](README.md) - General project info
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Security issues

---

**Security is everyone's responsibility. When in doubt, ask or review existing implementations.**
