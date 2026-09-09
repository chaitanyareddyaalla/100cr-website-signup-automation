# Worker operations

Workers atomically claim queued jobs, refresh heartbeats, classify failures, retry only transient errors with exponential backoff, and release or recover abandoned work after a lease expires. On shutdown, stop claiming new jobs and safely acknowledge or release the current job.

The only enabled adapter is mock mode. `AuthorizedPlaywrightAdapter` is opt-in and requires an explicit owned test URL plus a test-environment page marker.
