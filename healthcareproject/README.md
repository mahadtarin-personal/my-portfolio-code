# SmartHealth

Healthcare operations & patient engagement platform for MediNova

## Status

Core platform is under active implementation, now through Week 3 (event-driven system + observability). `profiles` and `booking` are real FastAPI services backed by Postgres (SQLAlchemy 2.0 + Alembic migrations) with JWT auth; `booking` also runs a Temporal saga (booking/reschedule/slot reconciliation), Celery (calendar sync, reminders, scheduled audit verification), and an outbox-to-Kafka relay. `notification` and `audit` are real Kafka-consumer services (not stubs) added in Week 3. `analytics` consumes the same event stream to compute business metrics. `billing` remains a Week-1 stub (health check only) — this section of the README describing services below has not been fully updated to reflect Week 2/3 additions (Temporal, Kafka, Celery, notification, audit) and should not be read as a complete architecture reference; see `docs/smarthealth_tech_flow_reference.html` and `deploy/docker-manual-commands.md` for the current picture instead.

The full stack now includes OpenTelemetry tracing (Jaeger), Prometheus + Grafana metrics dashboards, structured JSON logging, and Kafka consumer-lag monitoring — see **Observability** below.

## Docs

- [docs/SmartHealth - Guidelines.docx](docs/SmartHealth%20-%20Guidelines.docx) — execution plan, weekly milestones, submission/review process
- [docs/SmartHealth - Part A.docx](docs/SmartHealth%20-%20Part%20A.docx) — PRD for the core platform
- [docs/smarthealth_tech_flow_reference.html](docs/smarthealth_tech_flow_reference.html) — design reference (architecture, data model, service responsibilities, booking/visit/payment flows, idempotency, caching, observability, API contracts, security)

### Architecture Overview

![Architecture Overview](docs/SmartHealth%20-%20Architecture%20Overview.png)

Target-state system diagram (API gateway, all services, async workers, multi-zone HA). **Design reference, not as-built** — this repo has no Envoy gateway, no separate MongoDB-backed Clinical Records service, no Vault, and runs single-zone; see `deploy/docker-manual-commands.md` for what's actually deployed.

### Database Schema

![Database Schema](docs/SmartHealth%20-%20Database%20Schema.png)

Tables grouped by owning service, crow's-foot notation. **Design reference, not as-built** — `outbox` and `audit_log` match the real schema closely, and booking's `provider_schedule`/`time_off`/`slots`/`appointments` are real; but `billing` here shows a fully modeled table where the actual service is still a schema-less Week-1 stub, `clinical_records`/MongoDB doesn't exist in this repo, and analytics' real schema is just `analytics_events` — no separate `analytics_rollups` table, and no `notifications` table is shown at all despite `notification` being a real, implemented service.

### Booking Flow

![Booking Flow](docs/SmartHealth%20-%20Booking%20Flow.png)

Booking saga's steps mapped to the tables each one reads/writes. Design reference; `billing` in particular is still a Week-1 stub, not the authorizing service shown here.

### Booking Sequence

![Booking Sequence](docs/SmartHealth%20-%20Booking%20Sequence.png)

Sequence diagram of a booking request end-to-end, including saga compensation on failure. Closest of the three to what's actually implemented (Temporal saga, Celery calendar sync, outbox → Kafka fan-out all real) — the API gateway box is the one part that doesn't exist here; each service validates its own JWT directly instead.

## Structure

```
services/
  profiles/    — patients, providers, clinics, staff, auth (JWT issue), RBAC — implemented
  booking/     — slots, appointments (create/cancel) — implemented; reschedule/waitlist/saga not yet built
  billing/     — stub (health check only)
  analytics/   — stub (health check only)
libs/
  jwt_shared/  — shared JWT issue/verify + role-based auth dependency, used by profiles & booking
deploy/
  postgres/    — DB init script (creates per-service `profiles` and `booking` databases)
```

### profiles service

FastAPI app (`services/profiles/app`) exposing:

- `POST /auth/login` — authenticates and issues a JWT (role + subject id embedded)
- `POST /patients`, `GET /patients/{patient_id}`
- `POST /providers`, `GET /providers`, `GET /providers/{provider_id}`, `GET/PUT /providers/{provider_id}/schedule`, `POST /providers/{provider_id}/time-off`
- `POST /clinics`, `GET /clinics`, `GET /clinics/{clinic_id}`
- `POST /staff` (admin/front_desk accounts)
- `GET /health`

Models: `User`, `Patient`, `Provider`, `Clinic`, `ProviderSchedule`, `TimeOff`. Expanding provider schedules/time-off into bookable slots is a later phase.

### booking service

FastAPI app (`services/booking/app`) exposing:

- `GET /slots` — list open slots, optionally filtered by provider
- `POST /appointments` — book a slot (patient-only)
- `GET /appointments/{appointment_id}/status`
- `PATCH /appointments/{appointment_id}` — cancel only; reschedule/waitlist not implemented yet
- `GET /health`

Models: `Slot`, `Appointment`. Cross-service references (patient/provider ids) are not real foreign keys — each service owns its own database.

### libs/jwt_shared

Shared package providing `Role`, `TokenPayload` (now carrying a unique `jti` and `iat` per token), `create_access_token`/`decode_access_token`, and a `JWTAuth` FastAPI dependency (with `.require_roles(...)`) so each service can verify tokens issued by `profiles` without a network call back. Tokens are signed RS256 (asymmetric): `profiles` holds the private key and is the only signer, every other service verifies with the public key only — see `scripts/generate_jwt_keys.py` and `deploy/docker-manual-commands.md`'s "JWT keys (RS256)" section. Since `booking` has no private key, its own service-to-service calls into `profiles` (schedule/time-off lookups during slot generation) go through `POST /auth/service-token`, a separate endpoint gated by a narrow-purpose `SERVICE_AUTH_SECRET` (never the RSA keys).

## Tech stack

**In use today:** Python, FastAPI, SQLAlchemy 2.0, PostgreSQL (via `psycopg`), Alembic, PyJWT, Passlib (bcrypt), Redis (booking's slots cache), Kafka (event backbone, via the outbox pattern — see `deploy/docker-manual-commands.md`'s "Outbox pattern" section), Temporal (the booking saga, reschedule, slot reconciliation, and reminder scheduling — a durable `workflow.sleep()`, not Celery), Celery (fire-and-forget async work + scheduled jobs), OpenTelemetry + Jaeger (distributed tracing), Prometheus + Grafana (metrics dashboards), slowapi (rate limiting — `POST /auth/login` in profiles and `POST /appointments` in booking; in-memory storage, per-process, matches this project's single-instance-per-service deployment shape), Docker + Docker Compose, pytest + ruff.

**Not present:** MongoDB (never adopted — Postgres per-service databases used throughout instead), a schema registry for Kafka (event payloads are plain JSON, not Avro/Protobuf), rate limiting on any endpoint besides those two.

**Known observability gap:** tracing only covers the synchronous HTTP path — the Temporal worker, Kafka consumers, and Celery worker processes call `configure_logging()` but never `configure_tracing()`, so none of their work produces spans in Jaeger today.

## Setup

```
make up                 # docker compose up -d --build (postgres, profiles, booking, billing, analytics)
make migrate-profiles    # alembic upgrade head inside the profiles container
make migrate-booking     # alembic upgrade head inside the booking container
make test                # pytest -v in each of the four services
make down
```

`make up` only builds the four Week-1 services and does not work end-to-end
on this project's dev machine (Podman-on-Windows has no working
`docker-compose`/`podman-compose` — see the top of
`deploy/docker-manual-commands.md` for why, and the manual `docker run`
commands that stand in for it, covering every service added since,
including notification, audit, Temporal, Kafka, Celery, and the full
observability stack below).

Services are reachable at `localhost:8001` (profiles), `8002` (booking), `8003` (billing), `8004` (analytics), `8005` (notification), `8006` (audit). Postgres listens on `5432`; each service gets its own database (see `deploy/postgres/init-multiple-dbs.sql`). Override `POSTGRES_USER`/`POSTGRES_PASSWORD` via environment variables — defaults are dev-only. JWT signing/verification keys come from `jwt-keys.env` (profiles) / `jwt-public-key.env` (booking and other verifiers), generated once via `python scripts/generate_jwt_keys.py` — see `deploy/docker-manual-commands.md`'s "JWT keys (RS256)" section, never commit either file.

## Observability

- **Traces** — Jaeger UI at `localhost:16686`. Search by Service, or by
  Tags (`appointment_id=<uuid>`, `patient_id=<uuid>`) on booking's
  appointment endpoints, which tag the current span via
  `tracing_shared.tag_span()` instead of leaving you to guess a time
  window. In-memory only — traces don't survive a Jaeger restart.
- **Metrics & dashboards** — Prometheus at `localhost:9090`, Grafana at
  `localhost:3001` (anonymous Admin access, local-dev only). Two
  dashboards auto-provisioned: **Service Overview** (up/down, request
  rate, error rate, P95 latency, a service uptime-history timeline) and
  **Business & Pipeline Health** (outbox lag, booking funnel by status,
  saga failure rate, Kafka consumer lag, audit hash-chain status,
  analytics' business numbers).
- **Logs** — structured JSON to stdout via `logging_shared`, one line per
  event. Nothing aggregates these today (no Loki/ELK) — read them with
  `docker logs <container>` (broken via `docker`/`podman` remote on this
  machine; use `podman machine ssh "podman logs <name>"` instead).

Full manual run commands (including Jaeger/Prometheus/Grafana/kafka-exporter, which `docker-compose.yml` defines but can't actually start on this machine) are in `deploy/docker-manual-commands.md`'s **Observability** section.
