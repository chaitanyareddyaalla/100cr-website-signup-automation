# Database operations

Production tables are batches, jobs, authorized_test_identities, attempts, and events. Index jobs by `batch_id`, `status`, and `worker_id`; index attempts by `job_id`; enforce `UNIQUE(identifier)` on identities. Use Alembic migrations, take daily backups, define retention, and test restores before release.
