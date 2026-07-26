# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import io
from datetime import date, datetime
from typing import Annotated

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.auth import (
    AUTH,
    COOKIE_NAME,
    CSRF_COOKIE_NAME,
    SESSION_TTL,
    auth_configured,
    change_credentials,
    clear_login_failures,
    credentials_valid,
    current_username,
    csrf_token,
    csrf_valid,
    make_csrf_token,
    login_allowed,
    make_session_token,
    record_login_failure,
    safe_next_url,
    session_user,
    set_credentials,
)
from app.database import Base, SessionLocal, engine, get_db
from app.migrations import run_migrations
from app.models import ContractorSettings
from app.paths import DATA_DIR, PRIVATE_DIR, SIGNATURE_PATH, STATIC_DIR, TEMPLATE_DIR
from app.routes.clients import router as clients_router
from app.routes.orders import router as orders_router
from app.routes.pdfs import router as pdf_router



MAX_SIGNATURE_SIZE = 5 * 1024 * 1024
MIN_SIGNATURE_HEIGHT = 600
MAX_SIGNATURE_HEIGHT = 4000
NORMALIZED_SIGNATURE_HEIGHT = 608
MIN_SIGNATURE_WIDTH = 300
MAX_SIGNATURE_WIDTH = 4000


async def verify_csrf(request: Request) -> None:
    if request.method != "POST":
        return
    content_type = request.headers.get("content-type", "").lower()
    if not (
        content_type.startswith("application/x-www-form-urlencoded")
        or content_type.startswith("multipart/form-data")
    ):
        return
    form = await request.form()
    submitted = str(form.get("_csrf") or "")
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    session_token = request.cookies.get(COOKIE_NAME)
    if not csrf_valid(submitted, cookie_value, session_token):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Форма устарела или CSRF-токен недействителен.")


app = FastAPI(
    title="SelfDocs",
    docs_url=None,
    redoc_url=None,
    dependencies=[Depends(verify_csrf)],
)


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    return templates.TemplateResponse(
        request=request, name="error.html", status_code=403,
        context={"title": "Форма устарела", "message": getattr(exc, "detail", "Доступ запрещен.")},
    )

app.mount(
    "/static",
    StaticFiles(directory=STATIC_DIR),
    name="static",
)

templates = Jinja2Templates(
    directory=TEMPLATE_DIR,
)
templates.env.globals["csrf_token"] = csrf_token

Base.metadata.create_all(bind=engine)
run_migrations(engine)


def ensure_settings() -> None:
    with SessionLocal() as db:
        settings = db.get(ContractorSettings, 1)

        if settings is None:
            settings = ContractorSettings(
                id=1,
                acceptance_text=(
                    "В течение трех рабочих дней с момента получения "
                    "Акта сдачи-приемки услуг от Подрядчика Заказчик "
                    "обязан подписать Акт или в эти же сроки направить "
                    "мотивированные возражения. В случае неполучения "
                    "подписанного Акта или мотивированных возражений "
                    "услуги считаются оказанными в полном объеме и "
                    "надлежащего качества."
                ),
            )
            db.add(settings)
            db.commit()


ensure_settings()


app.include_router(clients_router)
app.include_router(orders_router)
app.include_router(pdf_router)


def parse_optional_date(value: str) -> date | None:
    value = value.strip()

    if not value:
        return None

    return datetime.strptime(value, "%Y-%m-%d").date()


def template_settings_value(settings: ContractorSettings) -> dict:
    return {
        "id": settings.id,
        "full_name": settings.full_name or "",
        "short_name": settings.short_name or "",
        "tax_status": settings.tax_status or "",
        "inn": settings.inn or "",
        "passport_series": settings.passport_series or "",
        "passport_number": settings.passport_number or "",
        "passport_issued_at": (
            settings.passport_issued_at.isoformat()
            if settings.passport_issued_at
            else ""
        ),
        "passport_issued_by": settings.passport_issued_by or "",
        "registration_address": settings.registration_address or "",
        "phone": settings.phone or "",
        "email": settings.email or "",
        "bank_name": settings.bank_name or "",
        "bank_account": settings.bank_account or "",
        "bank_bik": settings.bank_bik or "",
        "bank_corr_account": settings.bank_corr_account or "",
        "default_payment_days": settings.default_payment_days,
        "default_unit": settings.default_unit or "",
        "vat_text": settings.vat_text or "",
        "acceptance_text": settings.acceptance_text or "",
        "signature_filename": settings.signature_filename,
    }


def validate_and_save_signature(raw: bytes) -> None:
    if not raw:
        raise ValueError("Загружен пустой файл.")

    if len(raw) > MAX_SIGNATURE_SIZE:
        raise ValueError("Размер файла подписи превышает 5 МБ.")

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Файл не является корректным изображением.") from exc

    if image.format != "PNG":
        raise ValueError("Подпись должна быть загружена в формате PNG.")

    width, height = image.size

    if height < MIN_SIGNATURE_HEIGHT:
        raise ValueError(
            "Высота изображения подписи должна быть не менее "
            f"{MIN_SIGNATURE_HEIGHT} px. Загружено: {height} px."
        )

    if height > MAX_SIGNATURE_HEIGHT:
        raise ValueError(
            "Высота изображения подписи не должна превышать "
            f"{MAX_SIGNATURE_HEIGHT} px. Загружено: {height} px."
        )

    if not MIN_SIGNATURE_WIDTH <= width <= MAX_SIGNATURE_WIDTH:
        raise ValueError(
            "Ширина подписи должна находиться в диапазоне "
            f"{MIN_SIGNATURE_WIDTH}–{MAX_SIGNATURE_WIDTH} px. "
            f"Загружено: {width} px."
        )

    # Приводим изображение к RGBA.
    # Если исходный PNG без прозрачности, автоматически удаляем
    # белый или почти белый фон с сохранением сглаживания линий.
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
    else:
        rgb = image.convert("RGB")
        rgba = Image.new("RGBA", rgb.size)

        source_pixels = rgb.load()
        target_pixels = rgba.load()

        for y in range(rgb.height):
            for x in range(rgb.width):
                red, green, blue = source_pixels[x, y]

                # Белый фон становится полностью прозрачным.
                # Серые переходные пиксели сохраняются как полупрозрачные,
                # благодаря чему края подписи не становятся рваными.
                alpha = 255 - min(red, green, blue)

                if red >= 250 and green >= 250 and blue >= 250:
                    alpha = 0

                target_pixels[x, y] = (
                    red,
                    green,
                    blue,
                    alpha,
                )

    alpha_channel = rgba.getchannel("A")
    minimum_alpha, maximum_alpha = alpha_channel.getextrema()

    if maximum_alpha == 0:
        raise ValueError(
            "После удаления фона изображение оказалось пустым."
        )

    target_width = round(
        width * NORMALIZED_SIGNATURE_HEIGHT / height
    )

    rgba = rgba.resize(
        (target_width, NORMALIZED_SIGNATURE_HEIGHT),
        Image.Resampling.LANCZOS,
    )

    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)

    rgba.save(
        SIGNATURE_PATH,
        format="PNG",
        dpi=(600, 600),
        optimize=True,
    )

    SIGNATURE_PATH.chmod(0o600)



PUBLIC_PATHS = {"/health", "/login", "/setup"}


@app.middleware("http")
async def csrf_cookie_middleware(request: Request, call_next):
    session_token = request.cookies.get(COOKIE_NAME)
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)

    if not csrf_valid(cookie_value, cookie_value, session_token):
        cookie_value = make_csrf_token(session_token)

    request.state.csrf_token = cookie_value
    response = await call_next(request)

    # Обработчик входа меняет session cookie и заменяет токен в request.state.
    # Поэтому итоговое значение читаем после выполнения обработчика, а не из
    # локальной переменной, вычисленной для анонимной сессии до login POST.
    desired_token = request.state.csrf_token
    if request.cookies.get(CSRF_COOKIE_NAME) != desired_token:
        response.set_cookie(
            CSRF_COOKIE_NAME,
            desired_token,
            max_age=SESSION_TTL,
            httponly=True,
            samesite="strict",
            secure=AUTH.secure_cookie,
            path="/",
        )

    return response


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path

    if path.startswith("/static/") or path == "/health":
        return await call_next(request)

    if not auth_configured():
        if path == "/setup":
            return await call_next(request)
        return RedirectResponse(url="/setup", status_code=303)

    if path in {"/login", "/setup"}:
        return await call_next(request)

    user = session_user(request.cookies.get(COOKIE_NAME))
    if user is None:
        next_url = path
        if request.url.query:
            next_url += "?" + request.url.query
        return RedirectResponse(
            url=f"/login?next={next_url}",
            status_code=303,
        )

    request.state.user = user
    return await call_next(request)


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    if auth_configured():
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="setup.html",
        context={"error": None, "username": "admin"},
    )


@app.post("/setup", response_class=HTMLResponse)
async def setup_submit(request: Request):
    if auth_configured():
        return RedirectResponse(url="/login", status_code=303)

    form = await request.form()
    username = str(form.get("username") or "")
    password = str(form.get("password") or "")
    confirmation = str(form.get("password_confirmation") or "")

    try:
        if password != confirmation:
            raise ValueError("Пароли не совпадают.")
        set_credentials(username, password)
    except ValueError as exc:
        return templates.TemplateResponse(
            request=request,
            name="setup.html",
            status_code=400,
            context={"error": str(exc), "username": username},
        )

    session_token = make_session_token(username.strip())
    request.state.csrf_token = make_csrf_token(session_token)
    response = RedirectResponse(url="/settings", status_code=303)
    response.set_cookie(
        COOKIE_NAME, session_token, max_age=SESSION_TTL, httponly=True,
        samesite="strict", secure=AUTH.secure_cookie, path="/",
    )
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/orders/new"):
    if session_user(request.cookies.get(COOKIE_NAME)):
        return RedirectResponse(url="/orders/new", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "next_url": safe_next_url(next)},
    )



@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request):
    form = await request.form()
    username = str(form.get("username") or "")
    password = str(form.get("password") or "")
    next_url = safe_next_url(str(form.get("next") or "/orders/new"))

    client_key = request.client.host if request.client else "unknown"
    if not login_allowed(client_key):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            status_code=429,
            context={
                "error": "Слишком много попыток входа. Повтори через 5 минут.",
                "next_url": next_url,
            },
        )

    if not credentials_valid(username, password):
        record_login_failure(client_key)
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            status_code=401,
            context={
                "error": "Неверное имя пользователя или пароль.",
                "next_url": next_url,
            },
        )

    clear_login_failures(client_key)
    session_token = make_session_token(username)
    request.state.csrf_token = make_csrf_token(session_token)

    response = RedirectResponse(url=next_url, status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        session_token,
        max_age=SESSION_TTL,
        httponly=True,
        samesite="strict",
        secure=AUTH.secure_cookie,
        path="/",
    )
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")
    return response

@app.get("/")
def root():
    return RedirectResponse(
        url="/orders/new",
        status_code=303,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    saved: int | None = None,
    db: Session = Depends(get_db),
):
    settings = db.get(ContractorSettings, 1)

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "active_page": "settings",
            "settings": template_settings_value(settings),
            "auth_username": current_username() or "",
            "security_success": (
                "Учетные данные изменены." if saved == 2 else None
            ),
            "success": (
                "Настройки сохранены."
                if saved == 1
                else None
            ),
        },
    )


@app.post("/settings", response_class=HTMLResponse)
async def save_settings(
    request: Request,
    full_name: Annotated[str, Form()],
    short_name: Annotated[str, Form()],
    tax_status: Annotated[str, Form()],
    inn: Annotated[str, Form()],
    passport_series: Annotated[str, Form()] = "",
    passport_number: Annotated[str, Form()] = "",
    passport_issued_at: Annotated[str, Form()] = "",
    passport_issued_by: Annotated[str, Form()] = "",
    registration_address: Annotated[str, Form()] = "",
    phone: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    bank_name: Annotated[str, Form()] = "",
    bank_account: Annotated[str, Form()] = "",
    bank_bik: Annotated[str, Form()] = "",
    bank_corr_account: Annotated[str, Form()] = "",
    default_payment_days: Annotated[int, Form()] = 5,
    default_unit: Annotated[str, Form()] = "усл.",
    vat_text: Annotated[str, Form()] = "Без НДС",
    acceptance_text: Annotated[str, Form()] = "",
    delete_signature: Annotated[str | None, Form()] = None,
    signature: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    settings = db.get(ContractorSettings, 1)

    try:
        parsed_passport_date = parse_optional_date(passport_issued_at)

        if default_payment_days < 1:
            raise ValueError(
                "Срок оплаты должен составлять не менее одного дня."
            )


        if delete_signature == "1":
            if SIGNATURE_PATH.exists():
                SIGNATURE_PATH.unlink()

            settings.signature_filename = None

        if signature and signature.filename:
            raw = await signature.read()
            validate_and_save_signature(raw)
            settings.signature_filename = SIGNATURE_PATH.name

        settings.full_name = full_name.strip()
        settings.short_name = short_name.strip()
        settings.tax_status = tax_status.strip()
        settings.inn = inn.strip()

        settings.passport_series = passport_series.strip()
        settings.passport_number = passport_number.strip()
        settings.passport_issued_at = parsed_passport_date
        settings.passport_issued_by = passport_issued_by.strip()

        settings.registration_address = registration_address.strip()
        settings.phone = phone.strip()
        settings.email = email.strip()

        settings.bank_name = bank_name.strip()
        settings.bank_account = bank_account.strip()
        settings.bank_bik = bank_bik.strip()
        settings.bank_corr_account = bank_corr_account.strip()

        settings.default_payment_days = default_payment_days
        settings.default_unit = default_unit.strip()
        settings.vat_text = vat_text.strip()
        settings.acceptance_text = acceptance_text.strip()

        db.commit()

    except ValueError as exc:
        db.rollback()

        current = template_settings_value(settings)

        current.update({
            "full_name": full_name,
            "short_name": short_name,
            "tax_status": tax_status,
            "inn": inn,
            "passport_series": passport_series,
            "passport_number": passport_number,
            "passport_issued_at": passport_issued_at,
            "passport_issued_by": passport_issued_by,
            "registration_address": registration_address,
            "phone": phone,
            "email": email,
            "bank_name": bank_name,
            "bank_account": bank_account,
            "bank_bik": bank_bik,
            "bank_corr_account": bank_corr_account,
            "default_payment_days": default_payment_days,
            "default_unit": default_unit,
            "vat_text": vat_text,
            "acceptance_text": acceptance_text,
        })

        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            status_code=400,
            context={
                "active_page": "settings",
                "settings": current,
                "auth_username": current_username() or "",
                "error": str(exc),
            },
        )

    return RedirectResponse(
        url="/settings?saved=1",
        status_code=303,
    )


@app.post("/settings/security", response_class=HTMLResponse)
async def save_security_settings(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    current_password = str(form.get("current_password") or "")
    new_username = str(form.get("new_username") or "")
    new_password = str(form.get("new_password") or "")
    confirmation = str(form.get("new_password_confirmation") or "")

    try:
        username = change_credentials(
            current_password=current_password,
            new_username=new_username,
            new_password=new_password,
            new_password_confirmation=confirmation,
        )
    except ValueError as exc:
        settings = db.get(ContractorSettings, 1)
        return templates.TemplateResponse(
            request=request,
            name="settings.html",
            status_code=400,
            context={
                "active_page": "settings",
                "settings": template_settings_value(settings),
                "auth_username": new_username or current_username() or "",
                "security_error": str(exc),
            },
        )

    session_token = make_session_token(username)
    request.state.csrf_token = make_csrf_token(session_token)
    response = RedirectResponse(url="/settings?saved=2", status_code=303)
    response.set_cookie(
        COOKIE_NAME, session_token, max_age=SESSION_TTL, httponly=True,
        samesite="strict", secure=AUTH.secure_cookie, path="/",
    )
    return response


@app.get("/private/signature")
def signature_preview(
    db: Session = Depends(get_db),
):
    settings = db.get(ContractorSettings, 1)

    if not settings.signature_filename or not SIGNATURE_PATH.exists():
        return HTMLResponse(
            content="Подпись не загружена",
            status_code=404,
        )

    return FileResponse(
        path=SIGNATURE_PATH,
        media_type="image/png",
        headers={
            "Cache-Control": "no-store, private",
        },
    )
