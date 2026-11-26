# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from sqlalchemy import Engine, inspect, text

CURRENT_SCHEMA_VERSION = 4


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
        if current < 3:
            columns = {
                column["name"]
                for column in inspect(connection).get_columns("clients")
            }

            if "contract_number" not in columns:
                connection.execute(text(
                    "ALTER TABLE clients ADD COLUMN "
                    "contract_number VARCHAR(100) NOT NULL DEFAULT ''"
                ))

            if "contract_date" not in columns:
                connection.execute(text(
                    "ALTER TABLE clients ADD COLUMN contract_date DATE"
                ))

            connection.execute(text(
                "INSERT INTO schema_migrations(version) VALUES (3)"
            ))
            current = 3

        if current < 4:
            additions = {
                "clients": {
                    "numbering_mode": "VARCHAR(20) NOT NULL DEFAULT 'global'",
                    "next_document_number": "INTEGER NOT NULL DEFAULT 1",
                },
                "orders": {
                    "individual_document_number": "INTEGER",
                },
            }

            for table, fields in additions.items():
                existing = {
                    col["name"]
                    for col in inspect(connection).get_columns(table)
                }
                for name, definition in fields.items():
                    if name not in existing:
                        connection.execute(text(
                            f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                        ))

            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_orders_individual_number "
                "ON orders(client_id, individual_document_number) "
                "WHERE individual_document_number IS NOT NULL"
            ))

            connection.execute(text(
                "INSERT INTO schema_migrations(version) VALUES (4)"
            ))
            current = 4

        if current > CURRENT_SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema {current} is newer than application schema "
                f"{CURRENT_SCHEMA_VERSION}."
            )
