-- Enforces design doc §13 literally: "the audit table's database role
-- has INSERT-only permission — no UPDATE or DELETE grant exists at the
-- database level, so tampering isn't just detectable, it's blocked
-- outright." Run this once, after the audit database + audit_log table
-- exist (i.e. after `alembic upgrade head`, which runs as the privileged
-- smarthealth role). The audit service's own runtime DATABASE_URL then
-- connects as audit_writer instead of smarthealth — a real behavioral
-- difference, not just a note in a comment: audit_writer literally
-- cannot execute UPDATE/DELETE against audit_log, verified live by
-- attempting one and watching Postgres itself reject it.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'audit_writer') THEN
    CREATE ROLE audit_writer LOGIN PASSWORD 'audit-writer-dev-pass';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE audit TO audit_writer;
GRANT USAGE ON SCHEMA public TO audit_writer;
GRANT SELECT, INSERT ON audit_log TO audit_writer;
-- INSERT on the table alone does NOT include permission to advance the
-- id column's backing sequence — Postgres requires that separately.
-- Found live: the first deploy attempt failed with "permission denied
-- for sequence audit_log_id_seq" despite the table grant already being
-- in place.
GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO audit_writer;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM audit_writer;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM PUBLIC;
