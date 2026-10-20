"""Serialize demo migrations/seeding before starting a server process."""

import os
import subprocess
import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.bootstrap import configure_runtime_role
from app.config import Settings
from app.database import database


def prepare_database(settings):
    migration_url = os.environ.get("MIGRATION_DATABASE_URL", settings.database_url)
    if settings.environment == "production":
        runtime, migration = make_url(settings.database_url), make_url(migration_url)
        if (runtime.username == migration.username or runtime.host != migration.host
                or runtime.database != migration.database or runtime.port != migration.port):
            raise ValueError("Production needs separate runtime and migration users on the same database")
    engine, _ = database(migration_url)
    environment = dict(os.environ, DATABASE_URL=migration_url)
    environment.pop("MIGRATION_DATABASE_URL", None)
    try:
        with engine.connect() as lock:
            postgres = engine.dialect.name == "postgresql"
            if postgres:
                lock.execute(text("SELECT pg_advisory_lock(486321901)"))
            try:
                subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=environment)
                if os.environ.get("SEED_DEMO", "false").lower() == "true":
                    subprocess.run([sys.executable, "-m", "app.seed"], check=True, env=environment)
                if migration_url != settings.database_url:
                    configure_runtime_role(lock, settings.database_url)
            finally:
                if postgres:
                    lock.rollback()
                    lock.execute(text("SELECT pg_advisory_unlock(486321901)"))
                    lock.commit()
        engine.dispose()
    finally:
        engine.dispose()


def main():
    settings = Settings()
    try:
        prepare_database(settings)
    except Exception:
        # Driver errors can contain SQL literals; do not echo credentials or statements.
        raise SystemExit("Database bootstrap failed. Check migration access and the restricted runtime role.") from None
    os.environ.pop("MIGRATION_DATABASE_URL", None)
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--no-access-log",
        ],
    )


if __name__ == "__main__":
    main()
