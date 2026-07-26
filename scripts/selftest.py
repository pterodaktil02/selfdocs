from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth import csrf_valid, make_csrf_token, safe_next_url
from app.main import app


def iter_http_routes(
    routes: Iterable[object],
    seen: set[int] | None = None,
):
    """Обойти HTTP-маршруты, включая FastAPI _IncludedRouter."""

    if seen is None:
        seen = set()

    for route in routes:
        identity = id(route)

        if identity in seen:
            continue

        seen.add(identity)

        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)

        if path and methods:
            yield route

        original_router = getattr(
            route,
            "original_router",
            None,
        )

        if original_router is not None:
            nested = getattr(
                original_router,
                "routes",
                None,
            )

            if nested:
                yield from iter_http_routes(
                    nested,
                    seen,
                )

        nested = getattr(route, "routes", None)

        if nested:
            yield from iter_http_routes(
                nested,
                seen,
            )


def test_credentials_reject_unicode_username() -> None:
    from app.auth import credentials_valid

    assert not credentials_valid(
        "админ",
        "wrong-password",
    )


def test_auth_helpers() -> None:
    session_token = "selftest-session"
    token = make_csrf_token(session_token)

    assert csrf_valid(
        token,
        token,
        session_token,
    ), "Valid CSRF token rejected"

    assert not csrf_valid(
        "wrong-token",
        token,
        session_token,
    ), "Invalid CSRF form token accepted"

    assert not csrf_valid(
        token,
        "wrong-cookie",
        session_token,
    ), "Invalid CSRF cookie accepted"

    safe_cases = {
        "/": "/",
        "/orders": "/orders",
        "/orders/1/edit": "/orders/1/edit",
    }

    unsafe_cases = [
        "",
        "orders",
        "https://example.com",
        "http://example.com",
        "//example.com",
        r"/\example.com",
        r"\example.com",
        "/%5cexample.com",
        "/%2f%2fexample.com",
    ]

    for value, expected in safe_cases.items():
        assert safe_next_url(value) == expected

    for value in unsafe_cases:
        assert safe_next_url(value) == "/", (
            f"Unsafe next URL accepted: {value!r}"
        )


def test_routes() -> None:
    routes = list(
        iter_http_routes(app.routes)
    )

    route_pairs = [
        (
            route.path,
            tuple(
                sorted(route.methods or [])
            ),
        )
        for route in routes
    ]

    duplicates = [
        pair
        for pair, count in Counter(
            route_pairs
        ).items()
        if count > 1
    ]

    assert not duplicates, (
        "Duplicate HTTP routes found: "
        + ", ".join(
            f"{','.join(methods)} {path}"
            for path, methods in duplicates
        )
    )

    # OpenAPI уже содержит эффективные маршруты
    # после всех include_router().
    openapi_paths = set(
        app.openapi().get("paths", {})
    )

    required = {
        "/health",
        "/setup",
        "/login",
        "/logout",
        "/orders",
        "/orders/new",
        "/clients",
        "/settings",
        "/settings/security",
    }

    missing = required - openapi_paths

    assert not missing, (
        f"Missing routes: {sorted(missing)}"
    )


def main() -> None:
    test_auth_helpers()
    test_credentials_reject_unicode_username()
    test_routes()

    print("SelfDocs self-test: OK")


if __name__ == "__main__":
    main()
