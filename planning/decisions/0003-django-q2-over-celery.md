# ADR 0003 — django-q2 over Celery

**Status:** accepted

## Context

Recipe import (image/PDF/URL → LLM → draft) takes 10–60 seconds and cannot run
in the request cycle. This is a single-box homelab deployment, and
`/ops/api/jobs` — inspecting the queue without database access — is a stated
requirement.

## Decision

**django-q2 with the Django ORM broker.**

| Option | Extra infra | Job introspection |
|---|---|---|
| Celery + Redis | Redis + worker containers | needs flower or a result backend |
| dramatiq / Huey | broker container + worker | add-on |
| **django-q2** | **worker process only** | **built-in ORM models** |

Postgres is already a hard dependency, so the ORM broker means three containers
instead of four. And because `OrmQ`/`Task`/`Success`/`Failure` are ORM models,
`/ops/api/jobs` is a queryset rather than an integration with a separate result
backend — every other option needs result persistence bolted on to match.

`Q_CLUSTER = {"sync": True}` also gives inline execution for integration tests.

## Consequences

- The ORM broker polls and tops out in the hundreds of jobs per minute.
  Irrelevant when imports take tens of seconds and arrive at human rate.
- `retry` must exceed `timeout`, or a job re-runs while still executing. This is
  django-q's classic footgun and is commented in `settings.py`.
- All enqueues go through `imports/tasks.py`, never `async_task()` at call
  sites, so migrating to Django's built-in background tasks later is a one-file
  change.
