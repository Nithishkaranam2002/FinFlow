CREATE EXTENSION IF NOT EXISTS vector;

-- Let Temporal auto-setup create temporal / temporal_visibility on first boot.
ALTER USER finflow CREATEDB;
