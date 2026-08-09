"""Create every table in the configured database.

Safe to re-run: ``create_all`` skips tables that already exist. It does *not* alter tables whose
definition has changed — adding a column to an existing database is a migration, and this script
is not a migration tool. During development, delete ``workspace.db`` and re-run.

    python scripts/init_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import settings          # noqa: E402
from core.logging import get_logger       # noqa: E402
from db.base import Base, engine          # noqa: E402
import db.models                          # noqa: E402,F401  — registers every table

log = get_logger("init_db")


def main() -> int:
    dialect = "SQLite" if settings.is_sqlite() else "PostgreSQL"
    # Never print the URL itself — it carries the password in production.
    log.info("Creating tables on %s", dialect)
    Base.metadata.create_all(engine)
    log.info("Done. %d tables registered.", len(Base.metadata.tables))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
