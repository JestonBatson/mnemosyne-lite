"""Apply numbered SQL migrations to a PostgreSQL database."""
from __future__ import annotations

import os
from pathlib import Path

import psycopg


def main() -> None:
    database_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    migrations = sorted((Path(__file__).resolve().parents[1] / "migrations").glob("*.sql"))
    with psycopg.connect(database_url) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        for migration in migrations:
            if migration.name in applied:
                continue
            connection.execute(migration.read_text())
            connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (migration.name,))
            print(f"applied {migration.name}")


if __name__ == "__main__":
    main()
