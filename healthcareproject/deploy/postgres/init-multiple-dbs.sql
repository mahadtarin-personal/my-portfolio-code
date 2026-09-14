-- Service-per-database: profiles and booking each get their own database in
-- this shared Postgres instance. No cross-service foreign keys.
CREATE DATABASE profiles;
CREATE DATABASE booking;
CREATE DATABASE notification;
CREATE DATABASE audit;
CREATE DATABASE analytics;
