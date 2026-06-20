-- ============================================================
-- supabase_setup.sql
-- Run this ONCE in Supabase → SQL Editor before first ingest
-- ============================================================

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Table to track which Excel file was last ingested
--    (used by ingest.py to skip re-ingesting if file hasn't changed)
CREATE TABLE IF NOT EXISTS ingest_metadata (
    id          SERIAL PRIMARY KEY,
    file_hash   TEXT        NOT NULL,
    file_path   TEXT,
    chunk_count INTEGER,
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- Verify: after running ingest.py you should see row counts:
-- SELECT COUNT(*) FROM kpi_chunks;
-- ============================================================
