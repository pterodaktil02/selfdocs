# Copyright (C) 2026 pterodaktil02
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import date


def clean(value: object) -> str:
    return str(value or "").strip()


def validate_digits(
    value: object,
    *,
    label: str,
    lengths: set[int],
    required: bool = False,
) -> str:
    normalized = clean(value)
    if not normalized:
        if required:
            raise ValueError(f"{label} обязателен.")
        return ""
    if not normalized.isdigit() or len(normalized) not in lengths:
        expected = " или ".join(str(length) for length in sorted(lengths))
        raise ValueError(f"{label} должен содержать {expected} цифр.")
    return normalized


def validate_contract(number: object, issued_at: object) -> tuple[str, str]:
    number = clean(number)
    issued_at = clean(issued_at)

    if len(number) > 100:
        raise ValueError("Номер договора не должен превышать 100 символов.")

    if bool(number) != bool(issued_at):
        raise ValueError("Укажите одновременно номер и дату договора.")

    if issued_at:
        try:
            issued_at = date.fromisoformat(issued_at).isoformat()
        except ValueError as exc:
            raise ValueError("Указана неверная дата договора.") from exc

    return number, issued_at
