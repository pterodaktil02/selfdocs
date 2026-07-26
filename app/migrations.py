from __future__ import annotations

from sqlalchemy import Engine, text

CURRENT_SCHEMA_VERSION = 2


def run_migrations(engine: Engine) -> None:
    """Create migration ledger and record the current baseline.

    New schema changes must be added here as ordered, transactional steps before
    CURRENT_SCHEMA_VERSION is increased.
    """
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        ))
        current = connection.execute(
            text("SELECT COALESCE(MAX(version), 0) FROM schema_migrations")
        ).scalar_one()
        if current < 1:
            connection.execute(
                text("INSERT INTO schema_migrations(version) VALUES (1)")
            )
        if current < 2:
            duplicate = connection.execute(text(
                "SELECT inn, kpp, COUNT(*) FROM clients WHERE inn <> '' "
                "GROUP BY inn, kpp HAVING COUNT(*) > 1 LIMIT 1"
            )).first()
            if duplicate:
                raise RuntimeError(
                    "Невозможно создать уникальный индекс клиентов: "
                    f"найдены дубликаты ИНН/КПП {duplicate[0]}/{duplicate[1]}."
                )
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_clients_inn_kpp "
                "ON clients(inn, kpp) WHERE inn <> ''"
            ))
            connection.execute(text("INSERT INTO schema_migrations(version) VALUES (2)"))
            current = 2
        if current > CURRENT_SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema {current} is newer than application schema "
                f"{CURRENT_SCHEMA_VERSION}."
            )
