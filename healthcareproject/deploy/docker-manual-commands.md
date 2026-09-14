# Manual Docker commands (Windows / Podman workaround)

`docker compose up` (and `make up`, which just calls it) does not work on this
machine: the Podman-on-Windows setup has no `docker-compose`/`podman-compose`
binary by default, and the `podman-compose` package that fixes that has a bug
resolving the `dockerfile:` path under `build:` on Windows, failing with:

```
Error: no Containerfile or Dockerfile specified or found in context directory
```

The `docker-compose.yml` itself is correct — this is a local tooling
limitation, not a bug in the project. Until it's resolved, use the manual
commands below, which build the same images and reproduce the same network
topology (env vars, ports, service-name-as-hostname) by hand.

All commands assume Git Bash, run from the repo root (`E:\healthcareproject`).

## Running from PowerShell instead

`docker` resolves in Git Bash but not in PowerShell on some machines, because
`docker.exe`/`docker.bat` live in a directory that isn't on the PowerShell
`PATH` (e.g. `C:\Users\<you>\bin`, wherever Podman's Docker-compatible shims
got installed). Add it for the current session before running any of the
commands below in PowerShell:

```powershell
$env:PATH += ";C:\Users\<you>\bin"
```

This only affects the current PowerShell window — run it again in any new
window/tab before using `docker` there. It doesn't touch the permanent PATH
(no admin rights needed, nothing to undo).

## Quick stop / start (containers already exist)

```bash
# stop everything
docker stop postgres redis kafka kafka-ui kafka-exporter redis-exporter postgres-exporter celery-exporter temporal temporal-ui jaeger prometheus grafana profiles profiles-outbox-relay booking booking-worker booking-outbox-relay celery-worker celery-beat billing analytics analytics-worker notification notification-worker audit audit-worker

# start everything again later (postgres/temporal first isn't strictly
# required, but the dependents will just error/retry until they're ready)
docker start postgres redis kafka kafka-ui kafka-exporter redis-exporter postgres-exporter celery-exporter temporal temporal-ui jaeger prometheus grafana profiles profiles-outbox-relay booking booking-worker booking-outbox-relay celery-worker celery-beat billing analytics analytics-worker notification notification-worker audit audit-worker
```

Check status anytime with:

```bash
docker ps -a
```

Temporal Web UI: `http://localhost:8080` — shows the `booking-saga` task
queue, live workflow executions, and (once one runs) the compensating
activities firing in reverse order on a failed booking.

## Full teardown (removes the containers, keeps images/data)

```bash
docker rm -f postgres redis kafka kafka-ui kafka-exporter redis-exporter postgres-exporter celery-exporter temporal temporal-ui jaeger prometheus grafana profiles profiles-outbox-relay booking booking-worker booking-outbox-relay celery-worker celery-beat billing analytics analytics-worker notification notification-worker audit audit-worker
```

The named volume `smarthealth-pgdata` survives this, so seeded data is still
there next time `postgres` is recreated with
`-v smarthealth-pgdata:/var/lib/postgresql/data`.

## Full rebuild from scratch (after a code change)

```bash
# 0. make sure the Podman VM is up
podman machine start

# 1. one-time setup (skip if network/volume already exist)
docker network create smarthealth-net
docker volume create smarthealth-pgdata

# 2. build images (repeat only for services you changed)
cd /e/healthcareproject
docker build -f services/profiles/Dockerfile     -t smarthealth-profiles:local     .
docker build -f services/booking/Dockerfile      -t smarthealth-booking:local      .
docker build -f services/billing/Dockerfile      -t smarthealth-billing:local      .
docker build -f services/analytics/Dockerfile    -t smarthealth-analytics:local    .
docker build -f services/notification/Dockerfile -t smarthealth-notification:local .
docker build -f services/audit/Dockerfile        -t smarthealth-audit:local        .

# 3. remove old containers if they exist
docker rm -f postgres redis kafka kafka-ui kafka-exporter redis-exporter postgres-exporter celery-exporter temporal temporal-ui jaeger prometheus grafana profiles profiles-outbox-relay booking booking-worker booking-outbox-relay celery-worker celery-beat billing analytics analytics-worker notification notification-worker audit audit-worker 2>/dev/null

# 4. postgres — MSYS_NO_PATHCONV=1 is required in Git Bash, otherwise it
#    mangles the container-side path in the -v flag
MSYS_NO_PATHCONV=1 docker run -d --name postgres --network smarthealth-net \
  -e POSTGRES_USER=smarthealth -e POSTGRES_PASSWORD=smarthealth \
  -v smarthealth-pgdata:/var/lib/postgresql/data \
  -v "E:\healthcareproject\deploy\postgres\init-multiple-dbs.sql:/docker-entrypoint-initdb.d/init.sql" \
  -p 5432:5432 postgres:16-alpine

# 4b. redis — backs the slots cache-aside layer in booking/booking-worker
docker run -d --name redis --network smarthealth-net -p 6379:6379 redis:7-alpine

# 4c. kafka — single-node KRaft broker (no separate Zookeeper container),
#     backs the Week 3 event-driven system (kafka_shared producer/consumer).
#     auto.create.topics.enable=true means the 14 named topics get created
#     lazily on first publish — no separate topic-bootstrap step needed.
#     Dual listener: PLAINTEXT (advertised as kafka:9092) for containers on
#     smarthealth-net, EXTERNAL (advertised as localhost:29092) for anything
#     run from the host — a client that connects on one advertised address
#     and gets told to reconnect on the other will fail to resolve it.
docker run -d --name kafka --network smarthealth-net \
  -e KAFKA_NODE_ID=1 \
  -e KAFKA_PROCESS_ROLES=broker,controller \
  -e KAFKA_LISTENERS="PLAINTEXT://:9092,EXTERNAL://:29092,CONTROLLER://:9093" \
  -e KAFKA_ADVERTISED_LISTENERS="PLAINTEXT://kafka:9092,EXTERNAL://localhost:29092" \
  -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
  -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP="CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT,EXTERNAL:PLAINTEXT" \
  -e KAFKA_CONTROLLER_QUORUM_VOTERS="1@kafka:9093" \
  -e KAFKA_INTER_BROKER_LISTENER_NAME=PLAINTEXT \
  -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 \
  -e KAFKA_AUTO_CREATE_TOPICS_ENABLE=true \
  -p 9092:9092 -p 29092:29092 apache/kafka:3.9.0

# 4d. kafka-ui — browser UI for Kafka (topics, messages), same role as
#     temporal-ui below but for Kafka instead of Temporal.
docker run -d --name kafka-ui --network smarthealth-net \
  -e KAFKA_CLUSTERS_0_NAME=smarthealth \
  -e KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS=kafka:9092 \
  -p 8081:8080 provectuslabs/kafka-ui:latest

# 4e. kafka-exporter — turns Kafka's internal consumer-group offsets into
#     Prometheus metrics (kafka_consumergroup_lag), scraped by the `kafka`
#     job in deploy/prometheus/prometheus.yml. No config file, no volume —
#     it just needs to reach the broker.
docker run -d --name kafka-exporter --network smarthealth-net \
  -p 9308:9308 danielqsj/kafka-exporter:latest --kafka.server=kafka:9092

# 4e-i. redis-exporter — Redis's own memory/clients/hit-ratio metrics
#     (scraped by the `redis` job). Note this Redis instance backs BOTH
#     booking's slots cache-aside layer AND Celery's broker/result
#     backend — one exporter covers both roles since it's the same
#     process either way.
docker run -d --name redis-exporter --network smarthealth-net \
  -p 9121:9121 oliver006/redis_exporter:latest --redis.addr=redis://redis:6379

# 4e-ii. postgres-exporter — connects to the `postgres` maintenance
#     database (not any one service's own DB) since that's what gives it
#     cluster-wide visibility (pg_database_size_bytes/pg_locks_count
#     across every service's database, not just one).
docker run -d --name postgres-exporter --network smarthealth-net \
  -e DATA_SOURCE_NAME="postgresql://smarthealth:smarthealth@postgres:5432/postgres?sslmode=disable" \
  -p 9187:9187 quay.io/prometheuscommunity/postgres-exporter:latest

# 4e-iii. celery-exporter — listens to Celery task events over the SAME
#     Redis broker celery-worker/celery-beat already use (no polling,
#     event-driven) — task success/failure/retry counts, queue backlog,
#     worker heartbeats.
docker run -d --name celery-exporter --network smarthealth-net \
  -p 9808:9808 danihodovic/celery-exporter:latest --broker-url=redis://redis:6379/0

# 4f. jaeger — OTLP/HTTP trace collector + UI. Every service's
#     tracing_shared exports spans here (see libs/tracing_shared);
#     COLLECTOR_OTLP_ENABLED=true is required or the :4318 receiver never
#     starts. In-memory storage only — traces are lost on container
#     restart, there's no persistence configured.
docker run -d --name jaeger --network smarthealth-net \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 16686:16686 -p 4318:4318 jaegertracing/all-in-one:latest

# 4g. prometheus — scrapes every service's /metrics (or /prom-metrics for
#     analytics, see deploy/prometheus/prometheus.yml's comment) every 15s.
MSYS_NO_PATHCONV=1 docker run -d --name prometheus --network smarthealth-net \
  -v "E:\healthcareproject\deploy\prometheus\prometheus.yml:/etc/prometheus/prometheus.yml" \
  -p 9090:9090 prom/prometheus:latest

# 4h. grafana — dashboards auto-provisioned from
#     deploy/grafana/provisioning (datasource + both dashboard JSON files),
#     reloaded from disk every 30s (dashboards.yml's updateIntervalSeconds)
#     with no restart needed after editing a dashboard file. Anonymous
#     Admin access is local-dev-only, same posture as the shared dev JWT
#     secret used elsewhere in this project — do not carry this into any
#     shared/production environment.
MSYS_NO_PATHCONV=1 docker run -d --name grafana --network smarthealth-net \
  -e GF_AUTH_ANONYMOUS_ENABLED=true -e GF_AUTH_ANONYMOUS_ORG_ROLE=Admin \
  -v "E:\healthcareproject\deploy\grafana\provisioning:/etc/grafana/provisioning" \
  -p 3001:3000 grafana/grafana:latest

# 5. temporal — auto-setup creates its own `temporal`/`temporal_visibility`
#    databases in the shared postgres instance on every start (not just
#    first-init), so this works against the already-existing dev volume
#    without touching init-multiple-dbs.sql.
#
# DYNAMIC_CONFIG_FILE_PATH must point to a file that actually exists
# INSIDE the image — config/dynamicconfig/docker.yaml, not
# development-sql.yaml (that path doesn't exist in this image at all).
# Hit live: this was wrong for a long time and only ever logged as a
# non-fatal warning ("Unable to create dynamic config client... no such
# file or directory") — until a fresh `:latest` pull of the image made
# the exact same misconfiguration a hard, silent crash (exit 1, no panic
# trace in the logs at all) on next recreation. `:latest` moving out
# from under a previously-working config is exactly the risk of using a
# floating tag — worth pinning a specific version if this recurs.
#
# PROMETHEUS_ENDPOINT enables Temporal server's own internal Prometheus
# metrics (workflow/activity/task-queue counters — NOT the same as our
# services' HTTP metrics) — scraped by the `temporal` job in
# deploy/prometheus/prometheus.yml. No -p needed; Prometheus reaches it
# over smarthealth-net at temporal:9090, nothing published to the host.
docker run -d --name temporal --network smarthealth-net \
  -e DB=postgres12 -e DB_PORT=5432 \
  -e POSTGRES_USER=smarthealth -e POSTGRES_PWD=smarthealth -e POSTGRES_SEEDS=postgres \
  -e DYNAMIC_CONFIG_FILE_PATH=config/dynamicconfig/docker.yaml \
  -e PROMETHEUS_ENDPOINT=0.0.0.0:9090 \
  -p 7233:7233 temporalio/auto-setup:latest

docker run -d --name temporal-ui --network smarthealth-net \
  -e TEMPORAL_ADDRESS=temporal:7233 -e TEMPORAL_CORS_ORIGINS=http://localhost:3000 \
  -p 8080:8080 temporalio/ui:latest

# 5b. JWT keys (RS256) — one-time setup, before starting profiles or
#     booking. RS256 replaced the old shared-secret (HS256) model: profiles
#     is the only service that ever SIGNS a token (user login, or a
#     service-token grant — see below), every service only ever VERIFIES
#     with the public key. Run once:
#         python scripts/generate_jwt_keys.py
#     This writes two gitignored files at the repo root — never commit
#     either:
#       jwt-keys.env        JWT_PRIVATE_KEY + JWT_PUBLIC_KEY + SERVICE_AUTH_SECRET  (profiles only)
#       jwt-public-key.env  JWT_PUBLIC_KEY + SERVICE_AUTH_SECRET                    (booking, or any other verifier-only service)
#     Deliberately two separate files, not one — booking's --env-file
#     literally never has the private key available to it, not just
#     "doesn't happen to use it". SERVICE_AUTH_SECRET is a separate,
#     narrow-purpose shared secret (NOT the RSA keys) that authenticates
#     POST /auth/service-token — see that endpoint's docstring in
#     app/routers/auth.py for why booking needs it: under RS256 it has no
#     private key to self-mint a credential with anymore (the old
#     HS256-era self-minting relied on booking holding the same shared
#     secret used for verification, which meant any service holding that
#     secret could forge an admin token for itself).

# 6. app containers (booking/booking-worker retry their own Temporal
#    connection on startup, so exact ordering against step 5 isn't critical)
docker run -d --name profiles --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/profiles" \
  --env-file jwt-keys.env \
  -e BOOKING_BASE_URL="http://booking:8000" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  -p 8001:8000 smarthealth-profiles:local

# 6b. outbox relays — the ONLY things that actually call Kafka on behalf of
#     profiles/booking now (see "Outbox pattern" note below). Run their
#     migrations (below, step 7) before starting these, same ordering rule
#     as notification/audit — an unpublished backlog just waits harmlessly
#     either way, but there's no reason to make it wait longer than needed.
docker run -d --name profiles-outbox-relay --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/profiles" \
  --env-file jwt-keys.env \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  smarthealth-profiles:local python -m app.outbox_relay

docker run -d --name booking --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/booking" \
  --env-file jwt-public-key.env \
  -e TEMPORAL_ADDRESS="temporal:7233" -e TEMPORAL_NAMESPACE="default" -e TEMPORAL_TASK_QUEUE="booking-saga" \
  -e REDIS_URL="redis://redis:6379/0" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  -p 8002:8000 smarthealth-booking:local

docker run -d --name booking-worker --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/booking" \
  --env-file jwt-public-key.env \
  -e TEMPORAL_ADDRESS="temporal:7233" -e TEMPORAL_NAMESPACE="default" -e TEMPORAL_TASK_QUEUE="booking-saga" \
  -e REDIS_URL="redis://redis:6379/0" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  smarthealth-booking:local python -m app.worker

docker run -d --name booking-outbox-relay --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/booking" \
  --env-file jwt-public-key.env \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  smarthealth-booking:local python -m app.outbox_relay

# celery-worker + celery-beat — fire-and-forget async work that doesn't
# belong in the Temporal saga (calendar sync, reminders) plus scheduled
# jobs (nightly audit hash-chain check). Reuse the booking image and the
# same Redis instance already deployed for the slots cache, as both
# Celery's broker and its result backend — no new infra. Both containers
# use the SAME command's app (`app.celery_app`); the only difference is
# `worker` (executes tasks) vs `beat` (schedules periodic ones) — same
# split as booking/booking-worker, just for Celery instead of Temporal.
#
# --env-file google-calendar.env is REQUIRED on celery-worker specifically
# — it's the only container that calls the real Google Calendar API
# (app/tasks/calendar_sync.py). Without it, google_calendar_enabled
# defaults to False (app/core/config.py) and every sync silently no-ops:
# a CalendarSyncLog row still gets written with action=SYNCED, but
# external_event_id stays empty and nothing ever reaches Google — no
# error, no log line calling it out. Hit this live: several appointments
# synced "successfully" with an empty external_event_id because this file
# had never actually been wired into this command.
docker run -d --name celery-worker --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/booking" \
  --env-file jwt-public-key.env \
  -e REDIS_URL="redis://redis:6379/0" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  --env-file google-calendar.env \
  smarthealth-booking:local celery -A app.celery_app worker --loglevel=info

docker run -d --name celery-beat --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/booking" \
  --env-file jwt-public-key.env \
  -e REDIS_URL="redis://redis:6379/0" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  smarthealth-booking:local celery -A app.celery_app beat --loglevel=info

docker run -d --name billing --network smarthealth-net -p 8003:8000 smarthealth-billing:local

# analytics + analytics-worker — the analytics DB doesn't exist on a
# pre-Week-3 postgres volume; create it once with:
#   docker exec postgres psql -U smarthealth -d postgres -c "CREATE DATABASE analytics;"
#
# Same ordering rule as notification/audit below: migrate before starting
# analytics-worker, otherwise its backlog fails once per event and only a
# full worker restart replays it.
docker run -d --name analytics --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/analytics" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  -p 8004:8000 smarthealth-analytics:local

docker exec analytics alembic upgrade head

docker run -d --name analytics-worker --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/analytics" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  smarthealth-analytics:local python -m app.worker

# notification + notification-worker — the notification DB doesn't exist on
# a pre-Week-3 postgres volume; create it once with:
#   docker exec postgres psql -U smarthealth -d postgres -c "CREATE DATABASE notification;"
#
# IMPORTANT ORDERING GOTCHA (hit live, not hypothetical): start `notification`
# and run its migration BEFORE starting `notification-worker`. The worker
# has enable.auto.commit=False and only commits a Kafka offset after its
# handler succeeds (correct redelivery-on-failure design) — but if it starts
# consuming before the `notifications` table exists, every event in the
# backlog fails once, and since nothing ever got committed, only a full
# worker *restart* replays them from `earliest` again. Cheaper to just get
# the ordering right the first time.
docker run -d --name notification --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/notification" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  -p 8005:8000 smarthealth-notification:local

docker exec notification alembic upgrade head

docker run -d --name notification-worker --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/notification" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  smarthealth-notification:local python -m app.worker

# audit + audit-worker — connects as a RESTRICTED role (audit_writer), not
# the shared smarthealth role every other service uses. This is the design
# doc §13 requirement made real: audit_writer has SELECT+INSERT only, no
# UPDATE/DELETE — enforced by Postgres itself, verified live by attempting
# an UPDATE as audit_writer and watching it get rejected ("permission
# denied for table audit_log"), not just asserted in a comment.
#
# Setup, once per fresh postgres volume:
#   docker exec postgres psql -U smarthealth -d postgres -c "CREATE DATABASE audit;"
#   docker run --rm --network smarthealth-net \
#     -e DATABASE_URL="postgresql+psycopg://smarthealth:smarthealth@postgres:5432/audit" \
#     smarthealth-audit:local alembic upgrade head
#   docker exec -i postgres psql -U smarthealth -d audit < deploy/postgres/audit-grants.sql
# (Migrations must run as the privileged smarthealth role — audit_writer
# can't create tables. The grants script itself needs one more grant not
# obvious up front: GRANT INSERT on the table does NOT include permission
# to advance the id column's backing sequence — hit this live as
# "permission denied for sequence audit_log_id_seq" on first deploy;
# deploy/postgres/audit-grants.sql already includes the sequence grant now.)
#
# Same worker-after-migration ordering rule as notification applies here too.
docker run -d --name audit --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://audit_writer:audit-writer-dev-pass@postgres:5432/audit" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  -p 8006:8000 smarthealth-audit:local

docker run -d --name audit-worker --network smarthealth-net \
  -e DATABASE_URL="postgresql+psycopg://audit_writer:audit-writer-dev-pass@postgres:5432/audit" \
  -e KAFKA_BOOTSTRAP_SERVERS="kafka:9092" \
  smarthealth-audit:local python -m app.worker

# 7. migrations (only needed once per fresh postgres volume)
docker exec profiles alembic upgrade head
docker exec booking alembic upgrade head
```

## Celery (calendar sync, scheduled jobs)

`celery-worker`/`celery-beat` share `app/celery_app.py` in the booking
image, using the already-deployed `redis` container as both broker and
result backend. This is for fire-and-forget async work that doesn't belong
in the Temporal saga, and periodic jobs — not a replacement for Temporal
(the booking saga still needs retries-with-compensation, which Celery
doesn't give you) or the 24h slot-generation Schedule (already covered by
Temporal, see `app/worker.py`'s docstring for why that one deliberately
stayed off Celery).

Reminders are **not** a Celery task anymore — `ReminderWorkflow`
(`app/workflows/reminder.py`) durably sleeps until the reminder's eta via
`workflow.sleep()`, then runs the `send_reminder` activity. Started as an
ABANDON-policy child right after `confirm_appointment`/`swap_appointment_slot`
succeed, so `booking-worker` (the Temporal worker, not Celery) is what
actually runs it — see that section above. This replaced a real gap: a
bare `send_reminder_task.apply_async(eta=...)` call made outside the DB
transaction that recorded the reminder as SCHEDULED had no durability of
its own — a crash between the two left a SCHEDULED row with nothing ever
actually enqueued to honor it.

**Verify the broker/worker wiring round-trips** (`app/tasks/debug.py` —
not a saga step, just proves the plumbing before real tasks build on it):
```bash
docker exec celery-worker celery -A app.celery_app call booking.debug_task --args='["hello"]'
# → prints a task ID
CID=$(docker ps --filter name=celery-worker -q); docker logs "$CID" 2>&1 | tail -5
# → "debug_task received: hello" — the worker actually picked it up and ran it
```

**Real tasks on this app:** `sync_calendar_task`/`revert_calendar_sync` (saga
step 3, enqueued from `app/activities/booking.py`) and
`verify_audit_chain_task` — the design §13 nightly second layer for audit
integrity, calling audit's own `GET /audit/verify` and logging CRITICAL
("PAGE:") on a mismatch. Only `celery-beat` schedules that last one
(`verify-audit-chain-nightly`, 2am UTC daily, see `app/celery_app.py`'s
`beat_schedule`) — trigger it on demand the same way as the debug task:

**Calendar sync and reminders are visible without touching a DB or log** —
`GET http://localhost:8002/calendar-sync-log` and
`GET http://localhost:8002/reminders` (both `booking`, no auth, optional
`?appointment_id=` filter — see `app/routers/ops.py`), same debug-surface
precedent as notification's `GET /notifications` and audit's `GET /audit`.
Also in Postman under "6. Booking - Appointments".
```bash
docker exec celery-worker celery -A app.celery_app call booking.verify_audit_chain_task
CID=$(docker ps --filter name=celery-worker -q); docker logs "$CID" 2>&1 | tail -5
# → "audit hash chain verified clean (N rows)"
```

## Outbox pattern (profiles/booking → Kafka)

`profiles` and `booking` never call Kafka directly — `app/services/events.py::publish()`
only writes a row into that service's own `outbox_events` table, in the SAME
transaction as whatever business change triggered it (commits/rolls back
together — no "the appointment confirmed but the event silently vanished
because Kafka was down" gap). `profiles-outbox-relay` /
`booking-outbox-relay` are the only processes that actually talk to Kafka —
each polls its own `outbox_events` table every ~2s, publishes unpublished
rows with a blocking, delivery-confirmed call (`kafka_shared.publish_event_sync`,
different from the fire-and-forget `publish_event` every other Kafka
producer in this project uses), and only marks a row `published_at` once
Kafka has genuinely acknowledged it.

**Verify it survives a real Kafka outage:**
```bash
docker stop kafka
# book/cancel/reschedule an appointment, or update a schedule, via Postman —
# it should still succeed normally, not hang or fail
docker exec postgres psql -U smarthealth -d booking -c "select id, topic, published_at from outbox_events where published_at is null;"
# → the row is there, durably captured, even though Kafka was unreachable
docker start kafka
sleep 5
docker exec postgres psql -U smarthealth -d booking -c "select id, topic, published_at from outbox_events order by id desc limit 5;"
# → published_at is now set — the relay caught up on its own, nothing lost
```
`booking-outbox-relay`/`profiles-outbox-relay` have no HTTP port — check
either's alive with `docker logs <name>` (expect a "relay started" line).

Health check ports once running: profiles `8001`, booking `8002`,
billing `8003`, analytics `8004`, notification `8005`, audit `8006`,
temporal-ui `8080` — e.g. `curl http://localhost:8001/health`. Observability
UIs: Jaeger `16686`, Prometheus `9090`, Grafana `3001` (see the
"Observability" section below).
`booking-worker`, `notification-worker`, `audit-worker`, `analytics-worker`,
`celery-worker`, `celery-beat`, and both outbox relays have no HTTP port —
check any of them's alive with
`docker logs <name>` (expect a "worker started"/"relay started" line) or,
for booking, by watching the task queue's poller count in the Temporal
UI; for notification, by watching `GET http://localhost:8005/notifications`
grow after an event fires; for audit, `GET http://localhost:8006/audit/verify`
(`{"valid": true, ...}`) after any event fires anywhere in the system —
audit consumes every topic; for analytics, `GET http://localhost:8004/metrics`
(the 5 dashboard numbers) or `GET http://localhost:8004/events` for the raw
feed. `redis` has no HTTP port either — check it with
`docker exec redis redis-cli ping` (expect `PONG`), or inspect a cached
slots entry directly with `docker exec redis redis-cli get slots:provider:<id>`.
`kafka` has no HTTP port either — check it's accepting connections with
`MSYS_NO_PATHCONV=1 docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list`
(topics only appear after the first publish, since they're created lazily;
`MSYS_NO_PATHCONV=1` is required in Git Bash, same reason as postgres's `-v`
flag above — otherwise it mangles the container-side path into a Windows
one). Kafka UI: `http://localhost:8081`.

## Observability (OpenTelemetry + Jaeger, Prometheus + Grafana)

Three separate signal types, three separate tools — see each service's
`main.py` for `configure_tracing`/`instrument_fastapi` (traces) and
`instrument_metrics` (metrics), both from `libs/tracing_shared` and
`libs/metrics_shared`. **Only the synchronous HTTP path is traced** — every
service's own `main.py` calls `configure_tracing()`, but the worker
processes (`booking-worker`, `analytics-worker`, `notification-worker`,
`audit-worker`, `celery-worker`, both outbox relays) only call
`configure_logging()`, never `configure_tracing()`. So Temporal activities
and Kafka consumers currently produce zero spans — Jaeger only shows what
happened inside a request/response cycle.

**Traces (Jaeger, `http://localhost:16686`)** — pick Service, hit **Find
Traces**. Business identifiers (`appointment_id`, `patient_id`,
`provider_id`) are attached to booking's appointment endpoints via
`tracing_shared.tag_span()` (see `app/routers/appointments.py`) — search
by **Tags**, e.g. `appointment_id=<uuid>`, instead of guessing a time
window. Traces are in-memory only (no persistent storage configured) and
lost on container restart.

**Metrics (Prometheus, `http://localhost:9090`; Grafana, `http://localhost:3001`)**
— every service exposes `/metrics` (analytics uses `/prom-metrics`
instead, since `/metrics` there is already its own business-JSON
endpoint), scraped every 15s per `deploy/prometheus/prometheus.yml`.
Grafana ships two dashboards, both auto-provisioned from
`deploy/grafana/provisioning/dashboards/` (reloaded from disk every 30s,
no restart needed after editing the JSON — `docker restart grafana` only
speeds that up, doesn't cause it):
- **SmartHealth - Service Overview** — up/down, request rate, error rate,
  P95 latency per service, and a **Service Uptime History** state-timeline
  panel (`up{job=...}` graphed over time, not just current state) — widen
  the time picker past its default 30-minute window to see anything older.
- **SmartHealth - Business & Pipeline Health** — outbox lag (profiles +
  booking), the booking funnel by status, saga failure rate (derived from
  `smarthealth_appointments_by_status{status="failed"}`, the same status
  `mark_appointment_failed` sets when the saga compensates), Kafka
  consumer lag by group (via `kafka-exporter`), audit hash-chain status
  (cached 60s so a 15s scrape doesn't re-verify the whole chain every
  time), and analytics' business numbers as gauges.

**Verify the whole stack is actually wired, not just running:**
```bash
curl -s http://localhost:9090/api/v1/targets | python -c "
import json,sys
for t in json.load(sys.stdin)['data']['activeTargets']:
    print(t['labels'].get('job'), t['health'])
"
# → every job (profiles, booking, billing, analytics, notification, audit, kafka) should say "up"

curl -s http://localhost:16686/api/services
# → lists every service that has ever exported a span — note booking-worker/
#   analytics-worker/etc. will NOT appear here, per the tracing gap above
```

## Nuke everything, including data

```bash
docker rm -f postgres redis kafka kafka-ui kafka-exporter redis-exporter postgres-exporter celery-exporter temporal temporal-ui jaeger prometheus grafana profiles profiles-outbox-relay booking booking-worker booking-outbox-relay celery-worker celery-beat billing analytics analytics-worker notification notification-worker audit audit-worker
docker volume rm smarthealth-pgdata
docker network rm smarthealth-net
```

Use this only when a genuinely clean slate is needed (e.g. re-testing the
Postgres init script itself) — `init-multiple-dbs.sql` only runs against a
*fresh* volume, so the volume specifically must be removed, not just the
containers.
