"""
Migration Script: Transfer data from local SQLite (sports.db) to Supabase (PostgreSQL)

Usage:
    python migrate_to_supabase.py "postgresql://postgres.[ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres"
    OR set the DATABASE_URL environment variable:
    python migrate_to_supabase.py
"""

import os
import sys
import sqlite3
import psycopg2
from psycopg2.extras import execute_batch

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sports.db")

TABLES_IN_ORDER = [
    "users",
    "equipment",
    "loans",
    "loan_members",
    "audit_logs",
    "notifications",
]


def get_sqlite_conn():
    if not os.path.exists(SQLITE_PATH):
        raise FileNotFoundError(f"SQLite file not found at {SQLITE_PATH}")
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def migrate(db_url):
    print(f"[*] Reading data from SQLite: {SQLITE_PATH}")
    sqlite_conn = get_sqlite_conn()
    sqlite_cur = sqlite_conn.cursor()

    print("[*] Connecting to Supabase PostgreSQL...")
    pg_conn = psycopg2.connect(db_url)
    pg_cur = pg_conn.cursor()

    try:
        for table in TABLES_IN_ORDER:
            print(f"--- Migrating table '{table}' ---")
            sqlite_cur.execute(f"SELECT * FROM {table}")
            rows = sqlite_cur.fetchall()
            if not rows:
                print(f"  No rows found in SQLite for '{table}'. Skipping.")
                continue

            col_names = [col[0] for col in sqlite_cur.description]
            cols_joined = ", ".join(col_names)
            placeholders = ", ".join(["%s"] * len(col_names))

            insert_query = f"INSERT INTO {table} ({cols_joined}) VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING"

            batch_data = [tuple(row[col] for col in col_names) for row in rows]
            execute_batch(pg_cur, insert_query, batch_data)
            print(f"  Inserted {len(batch_data)} rows into '{table}'.")

            # Update PostgreSQL sequence to max(id) so subsequent inserts do not collide
            try:
                pg_cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table}")
            except Exception as e:
                print(f"  Notice: could not update sequence for {table}: {e}")

        pg_conn.commit()
        print("\n[SUCCESS] All data has been successfully migrated to Supabase!")

    except Exception as e:
        pg_conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise e
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL")
    if not url:
        print("[!] Error: No database URL provided.")
        print('    Usage: python migrate_to_supabase.py "postgresql://postgres:password@host:port/postgres"')
        print('    Or set DATABASE_URL environment variable.')
        sys.exit(1)

    migrate(url)
