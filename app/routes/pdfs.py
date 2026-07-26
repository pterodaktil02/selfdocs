# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

import io
import json
import logging
import re
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from num2words import num2words
from pypdf import PdfReader, PdfWriter
from sqlalchemy.orm import Session
from weasyprint import HTML

from app.auth import csrf_token
from app.database import get_db
from app.models import Order
from app.paths import RESOURCE_DIR, SIGNATURE_PATH, TEMPLATE_DIR



logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=TEMPLATE_DIR)
templates.env.globals["csrf_token"] = csrf_token

router = APIRouter(
    prefix="/orders",
    tags=["pdf"],
)


def parse_snapshot(value: str | None) -> dict:
    try:
        result = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}

    return result if isinstance(result, dict) else {}


def decimal_value(value) -> Decimal:
    return Decimal(str(value or 0))


def order_total(order: Order) -> Decimal:
    return sum(
        (
            decimal_value(item.quantity)
            * decimal_value(item.price)
            for item in order.items
        ),
        Decimal("0"),
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def format_decimal(value, places: int = 2) -> str:
    number = decimal_value(value)

    if places == 3:
        number = number.quantize(Decimal("0.001"))
        text = f"{number:,.3f}"
        text = text.rstrip("0").rstrip(".")
    else:
        number = number.quantize(Decimal("0.01"))
        text = f"{number:,.2f}"

    return (
        text
        .replace(",", "\u00a0")
        .replace(".", ",")
    )


def plural_ru(
    number: int,
    one: str,
    few: str,
    many: str,
) -> str:
    number = abs(number) % 100

    if 11 <= number <= 19:
        return many

    last_digit = number % 10

    if last_digit == 1:
        return one

    if 2 <= last_digit <= 4:
        return few

    return many


def amount_in_words(value: Decimal) -> str:
    value = value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    rubles = int(value)
    kopecks = int(
        (value - Decimal(rubles)) * 100
    )

    ruble_words = num2words(
        rubles,
        lang="ru",
    )

    ruble_name = plural_ru(
        rubles,
        "рубль",
        "рубля",
        "рублей",
    )

    kopeck_name = plural_ru(
        kopecks,
        "копейка",
        "копейки",
        "копеек",
    )

    result = (
        f"{ruble_words} {ruble_name} "
        f"{kopecks:02d} {kopeck_name}"
    )

    return result[:1].upper() + result[1:]


def document_context(
    order: Order,
    *,
    with_signature: bool,
) -> dict:
    client = parse_snapshot(
        order.client_snapshot_json
    )

    contractor = parse_snapshot(
        order.contractor_snapshot_json
    )

    total = order_total(order)

    items = []

    for item in sorted(
        order.items,
        key=lambda row: row.position,
    ):
        quantity = decimal_value(item.quantity)
        price = decimal_value(item.price)

        items.append(
            {
                "position": item.position,
                "description": item.description,
                "quantity": quantity,
                "quantity_text": format_decimal(
                    quantity,
                    places=3,
                ),
                "unit": item.unit,
                "price": price,
                "price_text": format_decimal(price),
                "sum": (
                    quantity * price
                ).quantize(Decimal("0.01")),
                "sum_text": format_decimal(
                    quantity * price
                ),
            }
        )

    signature_uri = None

    if with_signature and SIGNATURE_PATH.is_file():
        signature_uri = SIGNATURE_PATH.as_uri()

    return {
        "order": order,
        "items": items,
        "client": client,
        "contractor": contractor,
        "total": total,
        "total_text": format_decimal(total),
        "total_words": amount_in_words(total),
        "signature_uri": signature_uri,
        "with_signature": with_signature,
    }


def render_document(
    order: Order,
    *,
    document_type: str,
    with_signature: bool,
) -> bytes:
    template_names = {
        "invoice": "documents/invoice.html",
        "act": "documents/act.html",
        "appendix": "documents/appendix.html",
    }

    template_name = template_names.get(document_type)

    if template_name is None:
        raise ValueError(
            "Неизвестный тип документа."
        )

    template = templates.get_template(
        template_name
    )

    html = template.render(
        **document_context(
            order,
            with_signature=with_signature,
        )
    )

    return HTML(
        string=html,
        base_url=str(RESOURCE_DIR),
    ).write_pdf()


TRANSLIT_MAP = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g",
    "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e",
    "ю": "yu", "я": "ya",
})


def filename_slug(value: object, fallback: str) -> str:
    text = str(value or "").strip().lower()
    text = text.translate(TRANSLIT_MAP)

    # Убираем типовые организационно-правовые формы,
    # чтобы имя файла не начиналось с ooo/ao/ip.
    text = re.sub(
        r"^(ooo|ao|pao|oao|zao|ip)[-_ ]+",
        "",
        text,
    )

    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")

    return text[:60] or fallback


def document_filename(
    order: Order,
    *,
    document_type: str,
    with_signature: bool,
) -> str:
    client = parse_snapshot(order.client_snapshot_json)
    contractor = parse_snapshot(order.contractor_snapshot_json)

    client_name = (
        client.get("short_name")
        or client.get("full_name")
        or "zakazchik"
    )

    contractor_name = (
        contractor.get("short_name")
        or contractor.get("full_name")
        or "ispolnitel"
    )

    type_names = {
        "invoice": "schet",
        "act": "akt",
        "appendix": "prilozhenie",
        "bundle": "komplekt",
    }

    signature_suffix = (
        "s-podpisyu"
        if with_signature
        else "bez-podpisi"
    )

    date_text = order.document_date.isoformat()

    return (
        f"{type_names[document_type]}-"
        f"{filename_slug(client_name, 'zakazchik')}-"
        f"{filename_slug(contractor_name, 'ispolnitel')}-"
        f"{order.document_number}-"
        f"{date_text}-"
        f"{signature_suffix}.pdf"
    )


def pdf_response(
    content: bytes,
    filename: str,
) -> StreamingResponse:
    headers = {
        "Content-Disposition": (
            f'attachment; filename="{filename}"'
        )
    }

    return StreamingResponse(
        io.BytesIO(content),
        media_type="application/pdf",
        headers=headers,
    )


def get_order_or_404(
    db: Session,
    order_id: int,
):
    order = db.get(Order, order_id)

    if order is None:
        return None

    # Загружаем relationship до закрытия сессии.
    list(order.items)

    return order


@router.get("/{order_id}/pdf/document/{document_type}")
def download_document(
    order_id: int,
    document_type: str,
    signature: int = 0,
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)

    if order is None:
        return HTMLResponse(
            "Заказ не найден.",
            status_code=404,
        )

    if document_type not in {
        "invoice",
        "act",
        "appendix",
    }:
        return HTMLResponse(
            "Неизвестный документ.",
            status_code=404,
        )

    try:
        content = render_document(
            order,
            document_type=document_type,
            with_signature=bool(signature),
        )
    except Exception:
        logger.exception(
            "PDF generation failed: order=%s type=%s signature=%s",
            order_id, document_type, bool(signature),
        )
        return HTMLResponse(
            "Не удалось сформировать PDF. Подробности записаны в журнал приложения.",
            status_code=500,
        )

    filename = document_filename(
        order,
        document_type=document_type,
        with_signature=bool(signature),
    )

    return pdf_response(content, filename)


@router.get("/{order_id}/pdf/bundle")
def download_bundle(
    order_id: int,
    signature: int = 0,
    db: Session = Depends(get_db),
):
    order = get_order_or_404(db, order_id)

    if order is None:
        return HTMLResponse(
            "Заказ не найден.",
            status_code=404,
        )

    try:
        writer = PdfWriter()

        for document_type in (
            "invoice",
            "appendix",
            "act",
        ):
            content = render_document(
                order,
                document_type=document_type,
                with_signature=bool(signature),
            )

            reader = PdfReader(io.BytesIO(content))

            for page in reader.pages:
                writer.add_page(page)

        result = io.BytesIO()
        writer.write(result)
        result.seek(0)
    except Exception:
        logger.exception(
            "PDF bundle generation failed: order=%s signature=%s",
            order_id, bool(signature),
        )
        return HTMLResponse(
            "Не удалось сформировать комплект PDF. Подробности записаны в журнал приложения.",
            status_code=500,
        )

    filename = document_filename(
        order,
        document_type="bundle",
        with_signature=bool(signature),
    )

    headers = {
        "Content-Disposition": (
            f'attachment; filename="{filename}"'
        )
    }

    return StreamingResponse(
        result,
        media_type="application/pdf",
        headers=headers,
    )
