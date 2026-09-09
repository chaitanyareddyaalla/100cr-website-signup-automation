# Troubleshooting

If readiness fails, check database connectivity, Redis connectivity, and worker logs. If jobs stay RUNNING, inspect worker heartbeats and recover expired leases. If the frontend cannot receive events, verify the configured `FRONTEND_ORIGIN` and reverse-proxy buffering for SSE. Never add broad CORS origins as a workaround.
