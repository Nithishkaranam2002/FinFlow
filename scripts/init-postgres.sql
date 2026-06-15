CREATE EXTENSION IF NOT EXISTS vector;

-- Temporal auto-setup needs permission to create/use its databases
ALTER USER finflow CREATEDB;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal') THEN
    CREATE DATABASE temporal OWNER finflow;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal_visibility') THEN
    CREATE DATABASE temporal_visibility OWNER finflow;
  END IF;
END
$$;
