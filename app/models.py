# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ContractorSettings(Base):
    __tablename__ = "contractor_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    full_name: Mapped[str] = mapped_column(String(255), default="")
    short_name: Mapped[str] = mapped_column(String(100), default="")
    tax_status: Mapped[str] = mapped_column(String(100), default="Самозанятый")
    inn: Mapped[str] = mapped_column(String(20), default="")

    passport_series: Mapped[str] = mapped_column(String(20), default="")
    passport_number: Mapped[str] = mapped_column(String(30), default="")
    passport_issued_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    passport_issued_by: Mapped[str] = mapped_column(Text, default="")

    registration_address: Mapped[str] = mapped_column(Text, default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(255), default="")

    bank_name: Mapped[str] = mapped_column(String(255), default="")
    bank_account: Mapped[str] = mapped_column(String(30), default="")
    bank_bik: Mapped[str] = mapped_column(String(20), default="")
    bank_corr_account: Mapped[str] = mapped_column(String(30), default="")

    default_payment_days: Mapped[int] = mapped_column(Integer, default=5)
    default_unit: Mapped[str] = mapped_column(String(20), default="усл.")
    vat_text: Mapped[str] = mapped_column(String(100), default="Без НДС")
    acceptance_text: Mapped[str] = mapped_column(Text, default="")

    next_document_number: Mapped[int] = mapped_column(Integer, default=1)
    signature_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        Index("uq_clients_inn_kpp", "inn", "kpp", unique=True, sqlite_where=text("inn <> ''")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    full_name: Mapped[str] = mapped_column(String(500))
    short_name: Mapped[str] = mapped_column(String(255), default="")
    inn: Mapped[str] = mapped_column(String(20), default="")
    kpp: Mapped[str] = mapped_column(String(20), default="")
    legal_address: Mapped[str] = mapped_column(Text, default="")

    bank_name: Mapped[str] = mapped_column(String(255), default="")
    bank_bik: Mapped[str] = mapped_column(String(20), default="")
    bank_corr_account: Mapped[str] = mapped_column(String(30), default="")
    bank_account: Mapped[str] = mapped_column(String(30), default="")

    contact_name: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(50), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    comment: Mapped[str] = mapped_column(Text, default="")

    is_archived: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="client")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    document_number: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")

    document_date: Mapped[date] = mapped_column(Date, default=date.today)
    work_start_date: Mapped[date] = mapped_column(Date, default=date.today)
    work_end_date: Mapped[date] = mapped_column(Date, default=date.today)

    payment_days: Mapped[int] = mapped_column(Integer, default=5)
    note: Mapped[str] = mapped_column(Text, default="")

    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="RESTRICT"))
    client: Mapped["Client"] = relationship(back_populates="orders")

    client_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    contractor_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")

    template_version: Mapped[str] = mapped_column(String(20), default="v1")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))

    position: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=1)
    unit: Mapped[str] = mapped_column(String(20), default="усл.")
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)

    order: Mapped["Order"] = relationship(back_populates="items")
