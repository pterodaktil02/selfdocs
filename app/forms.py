from __future__ import annotations


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
