# creatoriqx-worker

Runs the Celery worker process for CreatorIQX (ADR 0003). Job *definitions*
live in `creatoriqx-api` (`creatoriqx_api.modules.jobs.infrastructure.tasks`),
owned by the `jobs` bounded context like everything else business-related;
this package is just the deployable entrypoint that starts a worker pointed
at that app, so a worker container never needs its own copy of task code.

## Run locally

```
uv run --package creatoriqx-worker celery -A creatoriqx_api.modules.jobs.infrastructure.celery_app.celery_app worker --loglevel=info
```

(Needs `creatoriqx-api`'s settings satisfied the same way the API does -
copy `.env.example` to `.env` and start Postgres/Redis with
`python scripts/dev.py up`.) A production container for this (non-root,
multi-stage) is P0-021's job; this package only needs to exist and run.
