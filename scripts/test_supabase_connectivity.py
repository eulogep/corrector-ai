#!/usr/bin/env python3
"""Vérifie une connexion PostgreSQL Supabase sans afficher de secret."""

from __future__ import annotations

import os
import sys

import psycopg


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERREUR: DATABASE_URL absente", file=sys.stderr)
        return 2

    try:
        with psycopg.connect(
            database_url,
            connect_timeout=10,
            sslmode="require",
            prepare_threshold=None,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_user, current_database()")
                current_user, current_database = cursor.fetchone()
        print(f"OK: utilisateur={current_user}; base={current_database}")
        return 0
    except Exception as exc:  # test de diagnostic contrôlé
        message = str(exc).replace(database_url, "[DATABASE_URL_REDACTED]")
        print(f"ERREUR: {type(exc).__name__}: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
