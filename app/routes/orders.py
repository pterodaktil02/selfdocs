# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import csrf_token
from app.database import get_db
from app.models import (
    Client,
    ContractorSettings,
    Order,
    OrderItem,
)
from app.paths import TEMPLATE_DIR
from app.forms import clean, validate_digits


templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.globals["csrf_token"] = csrf_token

router = APIRouter(
    prefix="/orders",
    tags=["orders"],
)


MAX_ORDER_ITEMS = 500

CLIENT_FIELDS = (
    "full_name",
    "short_name",
    "inn",
    "kpp",
    "legal_address",
    "bank_name",
    "bank_account",
    "bank_bik",
    "bank_corr_account",
    "contact_name",
    "phone",
    "email",
    "comment",
)


def model_snapshot(instance) -> dict:
    result = {}

    for column in instance.__table__.columns:
        value = getattr(instance, column.name)

        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = str(value)

        result[column.name] = value

    return result



def parse_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(clean(value))
    except ValueError as exc:
        raise ValueError(
            f"Поле «{label}» содержит неверную дату."
        ) from exc


def parse_decimal(
    value: str,
    *,
    label: str,
    positive: bool = False,
) -> Decimal:
    normalized = clean(value).replace(" ", "").replace(",", ".")

    try:
        result = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(
            f"Поле «{label}» должно содержать число."
        ) from exc

    if positive and result <= 0:
        raise ValueError(
            f"Поле «{label}» должно быть больше нуля."
        )

    return result


def posted_client(form) -> dict:
    values = {
        field: clean(form.get(f"client_{field}"))
        for field in CLIENT_FIELDS
    }

    values["inn"] = validate_digits(
        values["inn"],
        label="ИНН заказчика",
        lengths={10, 12},
        required=True,
    )

    values["kpp"] = validate_digits(
        values["kpp"],
        label="КПП заказчика",
        lengths={9},
    )

    values["bank_account"] = validate_digits(
        values["bank_account"],
        label="Расчетный счет заказчика",
        lengths={20},
    )

    values["bank_bik"] = validate_digits(
        values["bank_bik"],
        label="БИК заказчика",
        lengths={9},
    )

    values["bank_corr_account"] = validate_digits(
        values["bank_corr_account"],
        label="Корреспондентский счет заказчика",
        lengths={20},
    )

    if not values["full_name"]:
        raise ValueError(
            "Полное наименование заказчика обязательно."
        )

    return values


def client_values(instance: Client) -> dict:
    return {field: clean(getattr(instance, field, "")) for field in CLIENT_FIELDS}


def client_values_changed(client: Client, values: dict) -> bool:
    current = client_values(client)
    return any(current[field] != clean(values[field]) for field in CLIENT_FIELDS)


def resolve_existing_client(
    db: Session,
    *,
    selected_client_id: str,
    values: dict,
) -> Client | None:
    if selected_client_id.isdigit():
        selected = db.get(Client, int(selected_client_id))
        if selected is not None:
            return selected

    statement = select(Client).where(
        Client.inn == values["inn"],
        Client.kpp == values["kpp"],
    )
    return db.scalar(statement)


def require_client_update_decision(
    client: Client | None,
    values: dict,
    mode: str,
) -> None:
    if client is None or not client_values_changed(client, values):
        return
    if mode not in {"update", "one_time"}:
        raise ValueError(
            "Реквизиты заказчика изменены. Выбери: обновить карточку "
            "или использовать изменения только в этом заказе."
        )


def find_or_create_client(
    db: Session,
    *,
    selected_client_id: str,
    values: dict,
    update_client_card: bool,
) -> Client:
    client = resolve_existing_client(
        db,
        selected_client_id=selected_client_id,
        values=values,
    )

    if client is not None:
        if update_client_card:
            for field in CLIENT_FIELDS:
                setattr(client, field, values[field])
            db.flush()
        return client

    client = Client()

    for field in CLIENT_FIELDS:
        setattr(client, field, values[field])

    db.add(client)
    db.flush()

    return client


def parse_items(form) -> list[dict]:
    descriptions = form.getlist("item_description")
    quantities = form.getlist("item_quantity")
    units = form.getlist("item_unit")
    prices = form.getlist("item_price")

    row_count = max(
        len(descriptions),
        len(quantities),
        len(units),
        len(prices),
        0,
    )

    items = []

    for index in range(row_count):
        description = clean(
            descriptions[index]
            if index < len(descriptions)
            else ""
        )

        quantity_raw = clean(
            quantities[index]
            if index < len(quantities)
            else ""
        )

        unit = clean(
            units[index]
            if index < len(units)
            else ""
        )

        price_raw = clean(
            prices[index]
            if index < len(prices)
            else ""
        )

        # Количество 1 и единица "усл." стоят в новой строке
        # по умолчанию. Поэтому пустоту позиции определяем только
        # по описанию и цене.
        if not description and not price_raw:
            continue

        if not description:
            raise ValueError(
                f"В позиции {index + 1} не указано наименование услуги."
            )

        quantity = parse_decimal(
            quantity_raw,
            label=f"Количество в позиции {index + 1}",
            positive=True,
        )

        price = parse_decimal(
            price_raw,
            label=f"Цена в позиции {index + 1}",
        )

        if price < 0:
            raise ValueError(
                f"Цена в позиции {index + 1} не может быть отрицательной."
            )

        items.append(
            {
                "description": description,
                "quantity": quantity.quantize(
                    Decimal("0.001")
                ),
                "unit": unit or "усл.",
                "price": price.quantize(
                    Decimal("0.01")
                ),
            }
        )

    if not items:
        raise ValueError("Добавь хотя бы одну позицию услуги.")
    if len(items) > MAX_ORDER_ITEMS:
        raise ValueError(f"В одном заказе допускается не более {MAX_ORDER_ITEMS} позиций.")
    return items


def empty_form(settings: ContractorSettings) -> dict:
    today = date.today().isoformat()

    return {
        "document_date": today,
        "work_start_date": today,
        "work_end_date": today,
        "payment_days": settings.default_payment_days or 5,
        "note": "",
        "selected_client_id": "",
        "client_update_mode": "",
        "client": {
            field: ""
            for field in CLIENT_FIELDS
        },
        "items": [
            {
                "description": "",
                "quantity": "1",
                "unit": settings.default_unit or "усл.",
                "price": "",
            }
        ],
    }


def form_after_error(form) -> dict:
    descriptions = form.getlist("item_description")
    quantities = form.getlist("item_quantity")
    units = form.getlist("item_unit")
    prices = form.getlist("item_price")

    row_count = max(
        len(descriptions),
        len(quantities),
        len(units),
        len(prices),
        1,
    )

    items = []

    for index in range(row_count):
        items.append(
            {
                "description": (
                    descriptions[index]
                    if index < len(descriptions)
                    else ""
                ),
                "quantity": (
                    quantities[index]
                    if index < len(quantities)
                    else "1"
                ),
                "unit": (
                    units[index]
                    if index < len(units)
                    else "усл."
                ),
                "price": (
                    prices[index]
                    if index < len(prices)
                    else ""
                ),
            }
        )

    return {
        "document_date": clean(form.get("document_date")),
        "work_start_date": clean(form.get("work_start_date")),
        "work_end_date": clean(form.get("work_end_date")),
        "payment_days": clean(form.get("payment_days")),
        "note": clean(form.get("note")),
        "selected_client_id": clean(
            form.get("selected_client_id")
        ),
        "client_update_mode": clean(
            form.get("client_update_mode")
        ),
        "client": {
            field: clean(form.get(f"client_{field}"))
            for field in CLIENT_FIELDS
        },
        "items": items,
    }


@router.get("/new", response_class=HTMLResponse)
def new_order_page(
    request: Request,
    db: Session = Depends(get_db),
):
    settings = db.get(ContractorSettings, 1)

    if settings is None:
        return HTMLResponse(
            "Сначала заполни настройки исполнителя.",
            status_code=409,
        )

    return templates.TemplateResponse(
        request=request,
        name="order_form.html",
        context={
            "active_page": "new_order",
            "form": empty_form(settings),
            "selected_client_card": {},
            "page_title": "Оформление документов",
            "page_description": "",
            "form_action": "/orders/new",
            "is_editing": False,
        },
    )


@router.post("/new", response_class=HTMLResponse)
async def create_order(
    request: Request,
    db: Session = Depends(get_db),
):
    form = await request.form()
    settings = db.get(ContractorSettings, 1)

    if settings is None:
        return HTMLResponse(
            "Сначала заполни настройки исполнителя.",
            status_code=409,
        )

    existing_client = None

    try:
        document_date = parse_date(
            form.get("document_date"),
            "Дата документа",
        )

        work_start_date = parse_date(
            form.get("work_start_date"),
            "Начало работ",
        )

        work_end_date = parse_date(
            form.get("work_end_date"),
            "Окончание работ",
        )

        if work_end_date < work_start_date:
            if clean(form.get("date_changed")) == "end":
                work_start_date = work_end_date
            else:
                work_end_date = work_start_date

        payment_days_raw = clean(
            form.get("payment_days")
        )

        if (
            not payment_days_raw.isdigit()
            or int(payment_days_raw) < 0
            or int(payment_days_raw) > 365
        ):
            raise ValueError(
                "Срок оплаты должен быть числом от 0 до 365 дней."
            )

        payment_days = int(payment_days_raw)
        client_values = posted_client(form)
        items = parse_items(form)

        selected_client_id = clean(form.get("selected_client_id"))
        client_update_mode = clean(form.get("client_update_mode"))
        existing_client = resolve_existing_client(
            db,
            selected_client_id=selected_client_id,
            values=client_values,
        )
        require_client_update_decision(
            existing_client,
            client_values,
            client_update_mode,
        )
        client = find_or_create_client(
            db,
            selected_client_id=selected_client_id,
            values=client_values,
            update_client_card=(client_update_mode == "update"),
        )

        order = Order(
            document_number=None,
            status="created",
            document_date=document_date,
            work_start_date=work_start_date,
            work_end_date=work_end_date,
            payment_days=payment_days,
            note=clean(form.get("note")),
            client_id=client.id,
            client_snapshot_json=json.dumps(
                client_values,
                ensure_ascii=False,
            ),
            contractor_snapshot_json=json.dumps(
                model_snapshot(settings),
                ensure_ascii=False,
            ),
            template_version="v1",
        )

        for position, item in enumerate(items, start=1):
            order.items.append(
                OrderItem(
                    position=position,
                    description=item["description"],
                    quantity=item["quantity"],
                    unit=item["unit"],
                    price=item["price"],
                )
            )

        db.add(order)
        db.flush()

        # Формат номера: ГГГГММ + ID заказа минимум из четырех цифр.
        # Например: 2026070001.
        order.document_number = int(
            f"{document_date:%Y%m}{order.id:04d}"
        )

        db.commit()
        db.refresh(order)

    except ValueError as exc:
        db.rollback()

        return templates.TemplateResponse(
            request=request,
            name="order_form.html",
            status_code=400,
            context={
                "active_page": "new_order",
                "form": form_after_error(form),
                "selected_client_card": (
                    client_values(existing_client) if existing_client else {}
                ),
                "page_title": "Оформление документов",
                "page_description": (
                    "Исправь отмеченную ошибку и сохрани заказ."
                ),
                "form_action": "/orders/new",
                "is_editing": False,
                "error": str(exc),
            },
        )

    except Exception:
        db.rollback()
        raise

    return RedirectResponse(
        url=f"/orders/{order.id}",
        status_code=303,
    )


@router.get("/{order_id}", response_class=HTMLResponse)
def order_created_page(
    order_id: int,
    request: Request,
    saved: int | None = None,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        return HTMLResponse(
            "Заказ не найден.",
            status_code=404,
        )

    total = sum(
        (
            Decimal(str(item.quantity))
            * Decimal(str(item.price))
            for item in order.items
        ),
        Decimal("0"),
    ).quantize(Decimal("0.01"))

    client_snapshot = json.loads(
        order.client_snapshot_json or "{}"
    )

    return templates.TemplateResponse(
        request=request,
        name="order_created.html",
        context={
            "active_page": "new_order",
            "order": order,
            "client": client_snapshot,
            "total": total,
            "success": (
                "Изменения сохранены."
                if saved == 1
                else None
            ),
        },
    )


def order_form_values(order: Order) -> dict:
    client = json.loads(
        order.client_snapshot_json or "{}"
    )

    return {
        "document_date": order.document_date.isoformat(),
        "work_start_date": order.work_start_date.isoformat(),
        "work_end_date": order.work_end_date.isoformat(),
        "payment_days": order.payment_days,
        "note": order.note or "",
        "selected_client_id": str(order.client_id),
        "client_update_mode": "",
        "client": {
            field: clean(client.get(field))
            for field in CLIENT_FIELDS
        },
        "items": [
            {
                "description": item.description or "",
                "quantity": str(item.quantity),
                "unit": item.unit or "усл.",
                "price": str(item.price),
            }
            for item in sorted(
                order.items,
                key=lambda row: row.position,
            )
        ],
    }


def history_total(order: Order) -> Decimal:
    return sum(
        (
            Decimal(str(item.quantity))
            * Decimal(str(item.price))
            for item in order.items
        ),
        Decimal("0"),
    ).quantize(Decimal("0.01"))


def format_history_money(value: Decimal) -> str:
    text = f"{value:,.2f}"

    return (
        text
        .replace(",", "\u00a0")
        .replace(".", ",")
    )


@router.get("", response_class=HTMLResponse)
def orders_history(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
):
    orders = list(
        db.scalars(
            select(Order).order_by(
                Order.document_date.desc(),
                Order.document_number.desc(),
                Order.id.desc(),
            )
        ).all()
    )

    query_text = q.strip()

    rows = []

    for order in orders:
        client = json.loads(
            order.client_snapshot_json or "{}"
        )

        searchable = (
            str(order.document_number or ""),
            client.get("full_name") or "",
            client.get("short_name") or "",
            client.get("inn") or "",
        )

        if query_text:
            needle = query_text.casefold()

            if not any(
                needle in str(value).casefold()
                for value in searchable
            ):
                continue

        total = history_total(order)

        rows.append(
            {
                "order": order,
                "client": client,
                "total": total,
                "total_text": format_history_money(total),
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="orders.html",
        context={
            "active_page": "orders",
            "rows": rows,
            "query": query_text,
        },
    )


@router.get("/{order_id}/edit", response_class=HTMLResponse)
def edit_order_page(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        return HTMLResponse(
            "Заказ не найден.",
            status_code=404,
        )

    list(order.items)

    return templates.TemplateResponse(
        request=request,
        name="order_form.html",
        context={
            "active_page": "orders",
            "form": order_form_values(order),
            "selected_client_card": client_values(order.client),
            "document_number": order.document_number,
            "page_title": (
                f"Редактирование заказа № "
                f"{order.document_number}"
            ),
            "page_description": (
                "После сохранения документы будут "
                "формироваться по обновленным данным."
            ),
            "form_action": f"/orders/{order.id}/edit",
            "submit_text": "Сохранить изменения",
            "is_editing": True,
        },
    )


@router.post("/{order_id}/edit", response_class=HTMLResponse)
async def update_order(
    order_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        return HTMLResponse(
            "Заказ не найден.",
            status_code=404,
        )

    form = await request.form()

    try:
        document_date = parse_date(
            form.get("document_date"),
            "Дата документа",
        )

        work_start_date = parse_date(
            form.get("work_start_date"),
            "Начало работ",
        )

        work_end_date = parse_date(
            form.get("work_end_date"),
            "Окончание работ",
        )

        if work_end_date < work_start_date:
            if clean(form.get("date_changed")) == "end":
                work_start_date = work_end_date
            else:
                work_end_date = work_start_date

        payment_days_raw = clean(
            form.get("payment_days")
        )

        if (
            not payment_days_raw.isdigit()
            or int(payment_days_raw) < 0
            or int(payment_days_raw) > 365
        ):
            raise ValueError(
                "Срок оплаты должен быть числом от 0 до 365 дней."
            )

        client_values = posted_client(form)
        items = parse_items(form)

        selected_client_id = clean(form.get("selected_client_id"))
        client_update_mode = clean(form.get("client_update_mode"))
        existing_client = resolve_existing_client(
            db,
            selected_client_id=selected_client_id,
            values=client_values,
        )
        require_client_update_decision(
            existing_client,
            client_values,
            client_update_mode,
        )
        client = find_or_create_client(
            db,
            selected_client_id=selected_client_id,
            values=client_values,
            update_client_card=(client_update_mode == "update"),
        )

        order.document_date = document_date
        order.work_start_date = work_start_date
        order.work_end_date = work_end_date
        order.payment_days = int(payment_days_raw)
        order.note = clean(form.get("note"))

        order.client_id = client.id
        order.client_snapshot_json = json.dumps(
            client_values,
            ensure_ascii=False,
        )

        # Номер и снимок исполнителя намеренно сохраняем.
        # Редактирование заказа не должно внезапно менять
        # исполнителя на текущие настройки.

        order.items.clear()

        for position, item in enumerate(items, start=1):
            order.items.append(
                OrderItem(
                    position=position,
                    description=item["description"],
                    quantity=item["quantity"],
                    unit=item["unit"],
                    price=item["price"],
                )
            )

        db.commit()

    except ValueError as exc:
        db.rollback()

        return templates.TemplateResponse(
            request=request,
            name="order_form.html",
            status_code=400,
            context={
                "active_page": "orders",
                "form": form_after_error(form),
                "selected_client_card": client_values(order.client),
                "document_number": order.document_number,
                "page_title": (
                    f"Редактирование заказа № "
                    f"{order.document_number}"
                ),
                "page_description": (
                    "Исправь отмеченную ошибку и сохрани заказ."
                ),
                "form_action": f"/orders/{order.id}/edit",
                "submit_text": "Сохранить изменения",
                "is_editing": True,
                "error": str(exc),
            },
        )

    except Exception:
        db.rollback()
        raise

    return RedirectResponse(
        url=f"/orders/{order.id}?saved=1",
        status_code=303,
    )


@router.post("/{order_id}/delete")
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)

    if order is None:
        return HTMLResponse(
            "Заказ не найден.",
            status_code=404,
        )

    db.delete(order)
    db.commit()

    return RedirectResponse(
        url="/orders?deleted=1",
        status_code=303,
    )


