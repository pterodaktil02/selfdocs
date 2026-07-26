# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from collections import Counter

from app.main import app


def test_no_duplicate_routes():
    pairs = []
    for path, operations in app.openapi()['paths'].items():
        for method in operations:
            pairs.append((path, method.upper()))
    assert not [pair for pair, count in Counter(pairs).items() if count > 1]


def test_critical_routes_exist():
    paths = set(app.openapi()['paths'])
    required = {
        '/setup', '/login', '/logout', '/orders', '/orders/new',
        '/clients', '/settings', '/settings/security', '/health',
    }
    assert required <= paths
