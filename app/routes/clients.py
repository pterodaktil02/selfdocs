# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import csrf_token
from app.database import get_db
from app.models import Client, Order
from app.paths import TEMPLATE_DIR
from app.forms import validate_digits


templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.globals["csrf_token"] = csrf_token

router = APIRouter(
    prefix="/clients",
    tags=["clients"],
)


def client_to_dict(client: Client) -> dict:
    return {
        "id": client.id,
        "full_name": client.full_name or "",
        "short_name": client.short_name or "",
        "inn": client.inn or "",
        "kpp": client.kpp or "",
        "legal_address": client.legal_address or "",
        "bank_name": client.bank_name or "",
        "bank_account": client.bank_account or "",
        "bank_bik": client.bank_bik or "",
        "bank_corr_account": client.bank_corr_account or "",
        "contact_name": client.contact_name or "",
        "phone": client.phone or "",
        "email": client.email or "",
        "comment": client.comment or "",
    }



def apply_client_values(
    client: Client,
    *,
    full_name: str,
    short_name: str,
    inn: str,
    kpp: str,
    legal_address: str,
    bank_name: str,
    bank_account: str,
    bank_bik: str,
    bank_corr_account: str,
    contact_name: str,
    phone: str,
    email: str,
    comment: str,
) -> None:
    normalized_name = full_name.strip()

    if not normalized_name:
        raise ValueError(
            "Полное наименование заказчика обязательно."
        )

    client.full_name = normalized_name
    client.short_name = short_name.strip()

    client.inn = validate_digits(
        inn,
        label="ИНН",
        lengths={10, 12},
        required=True,
    )

    client.kpp = validate_digits(
        kpp,
        label="КПП",
        lengths={9},
    )

    client.legal_address = legal_address.strip()

    client.bank_name = bank_name.strip()

    client.bank_account = validate_digits(
        bank_account,
        label="Расчетный счет",
        lengths={20},
    )

    client.bank_bik = validate_digits(
        bank_bik,
        label="БИК",
        lengths={9},
    )

    client.bank_corr_account = validate_digits(
        bank_corr_account,
        label="Корреспондентский счет",
        lengths={20},
    )

    client.contact_name = contact_name.strip()
    client.phone = phone.strip()
    client.email = email.strip()
    client.comment = comment.strip()


@router.get("", response_class=HTMLResponse)
def list_clients(
    request: Request,
    q: str = "",
    saved: int | None = None,
    deleted: int | None = None,
    db: Session = Depends(get_db),
):
    statement = select(Client).order_by(
        Client.short_name.asc(),
        Client.full_name.asc(),
    )

    clients = list(db.scalars(statement).all())
    query_text = q.strip()

    if query_text:
        needle = query_text.casefold()

        clients = [
            client
            for client in clients
            if any(
                needle in value.casefold()
                for value in (
                    client.full_name or "",
                    client.short_name or "",
                    client.inn or "",
                    client.kpp or "",
                )
            )
        ]

    return templates.TemplateResponse(
        request=request,
        name="clients.html",
        context={
            "active_page": "clients",
            "clients": clients,
            "query": query_text,
            "success": (
                "Изменения сохранены."
                if saved == 1
                else "Заказчик удален." if deleted == 1 else None
            ),
        },
    )


@router.get("/{client_id}/edit", response_class=HTMLResponse)
def edit_client_page(
    client_id: int,
    request: Request,
    delete_blocked: int | None = None,
    db: Session = Depends(get_db),
):
    client = db.get(Client, client_id)

    if client is None:
        return HTMLResponse(
            "Заказчик не найден.",
            status_code=404,
        )

    order_count = len(
        list(
            db.scalars(
                select(Order.id).where(Order.client_id == client_id)
            ).all()
        )
    )

    return templates.TemplateResponse(
        request=request,
        name="client_form.html",
        context={
            "active_page": "clients",
            "client": client_to_dict(client),
            "order_count": order_count,
            "delete_blocked": delete_blocked == 1,
        },
    )


@router.post("/{client_id}/edit", response_class=HTMLResponse)
def update_client(
    client_id: int,
    request: Request,
    full_name: Annotated[str, Form()],
    inn: Annotated[str, Form()],
    short_name: Annotated[str, Form()] = "",
    kpp: Annotated[str, Form()] = "",
    legal_address: Annotated[str, Form()] = "",
    bank_name: Annotated[str, Form()] = "",
    bank_account: Annotated[str, Form()] = "",
    bank_bik: Annotated[str, Form()] = "",
    bank_corr_account: Annotated[str, Form()] = "",
    contact_name: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    comment: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
):
    client = db.get(Client, client_id)

    if client is None:
        return HTMLResponse(
            "Заказчик не найден.",
            status_code=404,
        )

    values = {
        "id": client_id,
        "full_name": full_name,
        "short_name": short_name,
        "inn": inn,
        "kpp": kpp,
        "legal_address": legal_address,
        "bank_name": bank_name,
        "bank_account": bank_account,
        "bank_bik": bank_bik,
        "bank_corr_account": bank_corr_account,
        "contact_name": contact_name,
        "phone": phone,
        "email": email,
        "comment": comment,
    }

    try:
        normalized_inn = validate_digits(
            inn,
            label="ИНН",
            lengths={10, 12},
            required=True,
        )

        normalized_kpp = validate_digits(
            kpp,
            label="КПП",
            lengths={9},
        )

        duplicate = db.scalar(
            select(Client).where(
                Client.inn == normalized_inn,
                Client.kpp == normalized_kpp,
                Client.id != client_id,
            )
        )

        if duplicate is not None:
            raise ValueError(
                "Другой заказчик с таким ИНН и КПП уже существует."
            )

        apply_client_values(
            client,
            full_name=full_name,
            short_name=short_name,
            inn=inn,
            kpp=kpp,
            legal_address=legal_address,
            bank_name=bank_name,
            bank_account=bank_account,
            bank_bik=bank_bik,
            bank_corr_account=bank_corr_account,
            contact_name=contact_name,
            phone=phone,
            email=email,
            comment=comment,
        )

        db.commit()

    except ValueError as exc:
        db.rollback()

        return templates.TemplateResponse(
            request=request,
            name="client_form.html",
            status_code=400,
            context={
                "active_page": "clients",
                "client": values,
                "error": str(exc),
                "order_count": db.scalar(
                    select(func.count(Order.id)).where(Order.client_id == client_id)
                ) or 0,
                "delete_blocked": False,
            },
        )

    return RedirectResponse(
        url="/clients?saved=1",
        status_code=303,
    )


@router.get("/api/search")
def search_clients(
    q: str = "",
    db: Session = Depends(get_db),
):
    query_text = q.strip().casefold()

    if not query_text:
        return JSONResponse([])

    clients = db.scalars(
        select(Client).order_by(
            Client.short_name.asc(),
            Client.full_name.asc(),
        )
    ).all()

    matches = []

    for client in clients:
        searchable_values = (
            client.full_name or "",
            client.short_name or "",
            client.inn or "",
            client.kpp or "",
        )

        if not any(
            query_text in value.casefold()
            for value in searchable_values
        ):
            continue

        matches.append(
            {
                "id": client.id,
                "full_name": client.full_name or "",
                "short_name": client.short_name or "",
                "inn": client.inn or "",
                "kpp": client.kpp or "",
                "label": (
                    client.short_name
                    or client.full_name
                    or f"Заказчик {client.id}"
                ),
            }
        )

        if len(matches) >= 10:
            break

    return JSONResponse(matches)


@router.get("/api/{client_id}")
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
):
    client = db.get(Client, client_id)

    if client is None:
        return JSONResponse(
            {"error": "Заказчик не найден."},
            status_code=404,
        )

    return JSONResponse(client_to_dict(client))


@router.post("/{client_id}/delete")
def delete_client(
    client_id: int,
    delete_orders: Annotated[int, Form()] = 0,
    db: Session = Depends(get_db),
):
    client = db.get(Client, client_id)

    if client is None:
        return HTMLResponse(
            "Заказчик не найден.",
            status_code=404,
        )

    orders = list(
        db.scalars(
            select(Order)
            .where(Order.client_id == client_id)
            .order_by(Order.id)
        ).all()
    )

    if orders and delete_orders != 1:
        return RedirectResponse(
            url=(
                f"/clients/{client_id}/edit"
                f"?delete_blocked=1"
            ),
            status_code=303,
        )

    for order in orders:
        db.delete(order)

    db.delete(client)
    db.commit()

    return RedirectResponse(
        url="/clients?deleted=1",
        status_code=303,
    )
