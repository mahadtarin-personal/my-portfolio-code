# Postgres init scripts

`init-multiple-dbs.sql` creates separate `profiles` and `booking` databases in one Postgres instance — service-per-database, no cross-service foreign keys. Mounted into `docker-entrypoint-initdb.d/` by `docker-compose.yml`, so it only runs on first container start (fresh volume).
