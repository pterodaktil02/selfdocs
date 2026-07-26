# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request


def fetch(url: str, cookie: str | None = None) -> tuple[int, str, bytes]:
    request = urllib.request.Request(url)
    if cookie:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.headers.get_content_type(), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get_content_type(), exc.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--cookie", help="selfdocs_session cookie value")
    parser.add_argument("--order-id", type=int)
    args = parser.parse_args()

    checks = [("health", "/health", 200, "application/json")]
    if args.cookie:
        checks += [
            ("root", "/", 200, "text/html"),
            ("orders", "/orders", 200, "text/html"),
            ("new order", "/orders/new", 200, "text/html"),
            ("clients", "/clients", 200, "text/html"),
            ("settings", "/settings", 200, "text/html"),
        ]
        if args.order_id:
            prefix = f"/orders/{args.order_id}"
            checks += [
                ("order", prefix, 200, "text/html"),
                ("edit", prefix + "/edit", 200, "text/html"),
                ("invoice", prefix + "/pdf/document/invoice", 200, "application/pdf"),
                ("appendix", prefix + "/pdf/document/appendix", 200, "application/pdf"),
                ("act", prefix + "/pdf/document/act", 200, "application/pdf"),
                ("bundle", prefix + "/pdf/bundle", 200, "application/pdf"),
            ]

    failed = False
    for name, path, expected_status, expected_type in checks:
        status, content_type, body = fetch(args.base + path, args.cookie)
        ok = status == expected_status and content_type == expected_type and bool(body)
        print(f"{'OK' if ok else 'FAIL'} {name}: {status} {content_type} {len(body)} bytes")
        failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
