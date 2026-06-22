"""
ingest_pms.py — Parse ALL BP PMS guides → embed → store in one Supabase table

Single table: pms_guide_chunks
Four sources: doc_source = 'employee'     → BP_PMS_Employee_Guideline.docx
              doc_source = 'line_manager' → Line_Manager_Guideline_Tutorial.docx
              doc_source = 'guidelines'   → Guidelines_Annual_Appraisal_2025-2026.docx
              doc_source = 'company_info' → About_Bachaa_Party.docx

Each doc's hash is tracked separately, so re-ingesting one never wipes the others.

Usage:
    python ingest_pms.py                      # ingest all four if changed
    python ingest_pms.py --force              # force re-ingest all four
    python ingest_pms.py --employee-only      # only employee doc
    python ingest_pms.py --lm-only            # only line manager doc
    python ingest_pms.py --guidelines-only    # only annual appraisal guidelines
    python ingest_pms.py --company-only       # only company info doc
    python ingest_pms.py path/emp.docx path/lm.docx   # custom paths (employee + LM only)
"""

from __future__ import annotations
import os
import sys
import argparse
import hashlib
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))
from pms_parser import (
    build_pms_chunks, build_lm_chunks,
    build_guidelines_chunks, build_company_info_chunks,
    PMSChunk,
)

# ── Config ─────────────────────────────────────────────────────────────────
DEFAULT_EMPLOYEE_DOCX   = "./data/BP_PMS_Employee_Guideline.docx"
DEFAULT_LM_DOCX         = "./data/Line_Manager_Guideline___Tutorial_for_the_Appraisal_System.docx"
DEFAULT_GUIDELINES_DOCX = "./data/Guidelines_Annual_Appraisal_2025-2026.docx"
DEFAULT_COMPANY_DOCX    = "./data/About_Bachaa_Party.docx"
EMBED_MODEL             = "all-MiniLM-L6-v2"
BATCH_SIZE              = 20
# ───────────────────────────────────────────────────────────────────────────


def get_db_url() -> str:
    url = os.getenv("SUPABASE_DB_URL", "")
    if not url:
        print("❌  SUPABASE_DB_URL not set in .env")
        sys.exit(1)
    return url


def connect(db_url: str):
    import psycopg2
    from pgvector.psycopg2 import register_vector
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    register_vector(conn)
    return conn


def create_table_if_needed(conn):
    """
    Create pms_guide_chunks with doc_source column.
    If the table already exists from a previous ingest (without doc_source),
    ALTER TABLE adds the column safely — existing rows default to 'employee'.
    """
    with conn.cursor() as cur:
        # Main chunks table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pms_guide_chunks (
                id             TEXT PRIMARY KEY,
                content        TEXT        NOT NULL,
                embedding      vector(384),
                section        TEXT        DEFAULT '',
                step_number    INTEGER     DEFAULT 0,
                step_title     TEXT        DEFAULT '',
                has_image      BOOLEAN     DEFAULT FALSE,
                image_filename TEXT        DEFAULT '',
                image_data     TEXT        DEFAULT '',
                chunk_type     TEXT        DEFAULT '',
                doc_source     TEXT        DEFAULT 'employee'
            );
        """)

        # Add doc_source if the table already existed without it
        cur.execute("""
            ALTER TABLE pms_guide_chunks
            ADD COLUMN IF NOT EXISTS doc_source TEXT DEFAULT 'employee';
        """)

        # Vector index
        cur.execute("""
            CREATE INDEX IF NOT EXISTS pms_guide_chunks_embedding_idx
            ON pms_guide_chunks
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 50);
        """)

        # Metadata table — add doc_source column if it doesn't exist yet
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pms_ingest_metadata (
                id           SERIAL PRIMARY KEY,
                file_hash    TEXT NOT NULL,
                file_path    TEXT NOT NULL,
                chunk_count  INTEGER,
                doc_source   TEXT DEFAULT 'employee',
                ingested_at  TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        cur.execute("""
            ALTER TABLE pms_ingest_metadata
            ADD COLUMN IF NOT EXISTS doc_source TEXT DEFAULT 'employee';
        """)

    conn.commit()
    print("✅  Table pms_guide_chunks ready (with doc_source column)")


def get_file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_last_hash(conn, doc_source: str) -> str | None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT file_hash FROM pms_ingest_metadata
                   WHERE doc_source = %s
                   ORDER BY ingested_at DESC LIMIT 1""",
                (doc_source,)
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def needs_reingest(conn, docx_path: str, doc_source: str) -> bool:
    current_hash = get_file_hash(docx_path)
    last_hash    = get_last_hash(conn, doc_source)
    if last_hash is None:
        print(f"  📦 [{doc_source}] No previous ingest — ingesting fresh...")
        return True
    if current_hash != last_hash:
        print(f"  📦 [{doc_source}] Document changed — re-ingesting...")
        return True
    return False


def clear_existing(conn, doc_source: str):
    """Delete only rows for this doc_source — the other source is untouched."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM pms_guide_chunks WHERE doc_source = %s", (doc_source,))
    conn.commit()
    print(f"  ♻️  Cleared existing [{doc_source}] chunks")


def store_chunks(conn, chunks: list[PMSChunk], model):
    """Embed and insert chunks. doc_source is read from each chunk object."""
    import psycopg2.extras

    print(f"  📥 Embedding {len(chunks)} chunks with {EMBED_MODEL}...")
    texts      = [c.content for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=32)

    print(f"  💾 Inserting into Supabase (includes image data)...")
    with conn.cursor() as cur:
        for i in tqdm(range(0, len(chunks), BATCH_SIZE), desc="  Inserting"):
            batch     = chunks[i:i + BATCH_SIZE]
            batch_emb = embeddings[i:i + BATCH_SIZE]

            records = []
            for chunk, emb in zip(batch, batch_emb):
                records.append((
                    chunk.chunk_id,
                    chunk.content,
                    emb.tolist(),
                    chunk.section,
                    chunk.step_number,
                    chunk.step_title,
                    chunk.has_image,
                    chunk.image_filename,
                    chunk.image_data,
                    chunk.chunk_type,
                    chunk.doc_source,
                ))

            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO pms_guide_chunks
                       (id, content, embedding, section, step_number, step_title,
                        has_image, image_filename, image_data, chunk_type, doc_source)
                   VALUES %s
                   ON CONFLICT (id) DO UPDATE SET
                       content        = EXCLUDED.content,
                       embedding      = EXCLUDED.embedding,
                       section        = EXCLUDED.section,
                       step_number    = EXCLUDED.step_number,
                       step_title     = EXCLUDED.step_title,
                       has_image      = EXCLUDED.has_image,
                       image_filename = EXCLUDED.image_filename,
                       image_data     = EXCLUDED.image_data,
                       chunk_type     = EXCLUDED.chunk_type,
                       doc_source     = EXCLUDED.doc_source""",
                records,
            )
    conn.commit()
    print(f"  ✅ {len(chunks)} chunks stored")


def save_metadata(conn, file_hash: str, file_path: str,
                  chunk_count: int, doc_source: str):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO pms_ingest_metadata
               (file_hash, file_path, chunk_count, doc_source)
               VALUES (%s, %s, %s, %s)""",
            (file_hash, os.path.abspath(file_path), chunk_count, doc_source),
        )
    conn.commit()


def _ingest_one(conn, docx_path: str, doc_source: str,
                build_fn, model, force: bool):
    """Ingest a single doc if its hash changed (or force=True)."""
    if not os.path.exists(docx_path):
        print(f"  ⚠️  [{doc_source}] File not found: {docx_path} — skipping")
        return 0

    if not force and not needs_reingest(conn, docx_path, doc_source):
        print(f"  ✅ [{doc_source}] Up to date — nothing to do.")
        return -1  # -1 = skipped

    chunks = build_fn(docx_path)
    clear_existing(conn, doc_source)
    store_chunks(conn, chunks, model)
    file_hash = get_file_hash(docx_path)
    save_metadata(conn, file_hash, docx_path, len(chunks), doc_source)
    return len(chunks)


def run_ingest(employee_docx: str, lm_docx: str,
               guidelines_docx: str = DEFAULT_GUIDELINES_DOCX,
               company_docx: str = DEFAULT_COMPANY_DOCX,
               force: bool = False,
               employee_only: bool = False,
               lm_only: bool = False,
               guidelines_only: bool = False,
               company_only: bool = False):

    # If any "*_only" flag is set, every other source is skipped.
    only_flags = [employee_only, lm_only, guidelines_only, company_only]
    any_only   = any(only_flags)

    do_employee   = employee_only   or not any_only
    do_lm         = lm_only         or not any_only
    do_guidelines = guidelines_only or not any_only
    do_company    = company_only    or not any_only

    db_url = get_db_url()
    conn   = connect(db_url)
    create_table_if_needed(conn)

    print("\n" + "=" * 55)
    print("  BP PMS Guides — Supabase Ingest")
    print("=" * 55)

    print(f"\n🤖  Loading embedding model ({EMBED_MODEL})...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL)

    emp_count    = 0
    lm_count     = 0
    guide_count  = 0
    company_count = 0

    if do_employee:
        print(f"\n── Employee Guide ──────────────────────────────────")
        print(f"   {os.path.abspath(employee_docx)}")
        emp_count = _ingest_one(
            conn, employee_docx, "employee",
            build_pms_chunks, model, force,
        )

    if do_lm:
        print(f"\n── Line Manager Guide ──────────────────────────────")
        print(f"   {os.path.abspath(lm_docx)}")
        lm_count = _ingest_one(
            conn, lm_docx, "line_manager",
            build_lm_chunks, model, force,
        )

    if do_guidelines:
        print(f"\n── Annual Appraisal Guidelines ─────────────────────")
        print(f"   {os.path.abspath(guidelines_docx)}")
        guide_count = _ingest_one(
            conn, guidelines_docx, "guidelines",
            build_guidelines_chunks, model, force,
        )

    if do_company:
        print(f"\n── About Bachaa Party (company info) ───────────────")
        print(f"   {os.path.abspath(company_docx)}")
        company_count = _ingest_one(
            conn, company_docx, "company_info",
            build_company_info_chunks, model, force,
        )

    conn.close()

    print("\n" + "=" * 55)
    if emp_count > 0:
        print(f"  ✅ Employee Guide        : {emp_count} chunks stored")
    elif emp_count == -1:
        print(f"  ✅ Employee Guide        : already up to date")

    if lm_count > 0:
        print(f"  ✅ Line Manager Guide    : {lm_count} chunks stored")
    elif lm_count == -1:
        print(f"  ✅ Line Manager Guide    : already up to date")

    if guide_count > 0:
        print(f"  ✅ Annual Guidelines     : {guide_count} chunks stored")
    elif guide_count == -1:
        print(f"  ✅ Annual Guidelines     : already up to date")

    if company_count > 0:
        print(f"  ✅ Company Info          : {company_count} chunks stored")
    elif company_count == -1:
        print(f"  ✅ Company Info          : already up to date")

    print("\n🎉  Done! Deploy the updated app.py and rag_engine.py\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Ingest BP PMS guides (employee, line manager, guidelines, company info) into Supabase"
    )
    ap.add_argument("employee_docx", nargs="?", default=DEFAULT_EMPLOYEE_DOCX,
                    help="Path to employee guideline docx")
    ap.add_argument("lm_docx", nargs="?", default=DEFAULT_LM_DOCX,
                    help="Path to line manager guideline docx")
    ap.add_argument("--guidelines-docx", default=DEFAULT_GUIDELINES_DOCX,
                    help="Path to Annual Appraisal Guidelines docx")
    ap.add_argument("--company-docx", default=DEFAULT_COMPANY_DOCX,
                    help="Path to About Bachaa Party docx")
    ap.add_argument("--force",            action="store_true", help="Force re-ingest all docs")
    ap.add_argument("--employee-only",    action="store_true", help="Only ingest employee doc")
    ap.add_argument("--lm-only",          action="store_true", help="Only ingest line manager doc")
    ap.add_argument("--guidelines-only",  action="store_true", help="Only ingest annual appraisal guidelines")
    ap.add_argument("--company-only",     action="store_true", help="Only ingest company info doc")
    args = ap.parse_args()

    run_ingest(
        employee_docx=args.employee_docx,
        lm_docx=args.lm_docx,
        guidelines_docx=args.guidelines_docx,
        company_docx=args.company_docx,
        force=args.force,
        employee_only=args.employee_only,
        lm_only=args.lm_only,
        guidelines_only=args.guidelines_only,
        company_only=args.company_only,
    )