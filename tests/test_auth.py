# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from app.auth import csrf_valid, make_csrf_token, safe_next_url


def test_safe_next_url():
    assert safe_next_url('/orders/new') == '/orders/new'
    assert safe_next_url('//evil.example') == '/'
    assert safe_next_url('/\\evil.example') == '/'
    assert safe_next_url('https://evil.example') == '/'


def test_csrf_is_session_bound():
    token = make_csrf_token('session-a')
    assert csrf_valid(token, token, 'session-a')
    assert not csrf_valid(token, token, 'session-b')
    assert not csrf_valid(token, 'wrong', 'session-a')
