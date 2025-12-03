#!/usr/bin/env python3
"""
Fix NULL values in anime_api.projects table that are causing API validation errors
"""
import psycopg2
from datetime import datetime

# Database connection
conn = psycopg2.connect(
    host="localhost",
    database="anime_production",
    user="patrick",
    password="***REMOVED***"
)

def fix_null_values():
    """Fix NULL values in projects table"""
    cur = conn.cursor()

    # Fix NULL status values
    print("Fixing NULL status values...")
    cur.execute("""
        UPDATE anime_api.projects
        SET status = 'created'
        WHERE status IS NULL OR status = ''
    """)
    print(f"  Updated {cur.rowcount} rows")

    # Fix NULL created_at values
    print("Fixing NULL created_at values...")
    cur.execute("""
        UPDATE anime_api.projects
        SET created_at = NOW()
        WHERE created_at IS NULL
    """)
    print(f"  Updated {cur.rowcount} rows")

    # Fix NULL description values
    print("Fixing NULL description values...")
    cur.execute("""
        UPDATE anime_api.projects
        SET description = ''
        WHERE description IS NULL
    """)
    print(f"  Updated {cur.rowcount} rows")

    # Commit changes
    conn.commit()

    # Verify the fix
    print("\nVerifying fixes...")
    cur.execute("""
        SELECT id, name, status, created_at,
               CASE WHEN description IS NULL THEN 'NULL' ELSE 'OK' END as desc_status
        FROM anime_api.projects
    """)

    for row in cur.fetchall():
        print(f"  Project {row[0]}: {row[1]} - Status: {row[2]}, Created: {row[3]}, Desc: {row[4]}")

    cur.close()

if __name__ == "__main__":
    fix_null_values()
    conn.close()
    print("\nDatabase fixes completed!")