# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.models import Client, ContractorSettings


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        settings = db.get(ContractorSettings, 1)
        if settings is None:
            settings = ContractorSettings(id=1)
            db.add(settings)

        settings.full_name = "Иванов Иван Иванович"
        settings.short_name = "Иванов И.И."
        settings.tax_status = "Самозанятый"
        settings.inn = "000000000000"
        settings.registration_address = "Демонстрационный адрес"
        settings.phone = "+7 000 000-00-00"
        settings.email = "demo@example.invalid"
        settings.bank_name = "Демонстрационный банк"
        settings.bank_account = "00000000000000000000"
        settings.bank_bik = "000000000"
        settings.bank_corr_account = "00000000000000000000"

        client = db.scalar(select(Client).where(Client.inn == "0000000000"))
        if client is None:
            client = Client(inn="0000000000", kpp="000000000")
            db.add(client)
        client.full_name = 'ООО "Рога и копыта"'
        client.short_name = 'ООО "Рога и копыта"'
        client.legal_address = "Демонстрационный адрес"
        client.bank_name = "Демонстрационный банк"
        client.bank_account = "00000000000000000000"
        client.bank_bik = "000000000"
        client.bank_corr_account = "00000000000000000000"
        client.email = "client@example.invalid"

        db.commit()
    print("Demo settings and client created. Values are fictional.")


if __name__ == "__main__":
    main()
