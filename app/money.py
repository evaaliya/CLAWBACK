"""Money helpers: integer cents only. Never store floats."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


class MoneyParseError(ValueError):
    """Raised when an amount cannot be converted to integer cents."""


def dollars_to_cents(value: Any) -> int:
    """Convert a dollar amount (str/int/Decimal) to integer cents.

    Accepts values like ``"-8.00"``, ``8``, ``Decimal("64.30")``.
    Rejects floats to avoid binary rounding (pass a string or Decimal instead).
    """
    if isinstance(value, float):
        raise MoneyParseError(
            "float amounts are not allowed; pass a string or Decimal"
        )
    if isinstance(value, int) and not isinstance(value, bool):
        # Bare int is treated as whole dollars (e.g. statement without decimals).
        return value * 100
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise MoneyParseError(f"cannot parse money value: {value!r}") from exc
    cents = (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def assert_cents(value: Any) -> int:
    """Coerce and validate that a stored amount is integer cents."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise MoneyParseError(f"amount must be int cents, got {type(value).__name__}")
    return value
