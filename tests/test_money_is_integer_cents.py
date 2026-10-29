"""T4 — Money is integer cents (schema and parser)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.db import MONEY_COLUMNS, money_column_types
from app.money import MoneyParseError, assert_cents, dollars_to_cents
from app.seed import seed_statement


def test_money_is_integer_cents(conn, demo_dir: Path) -> None:
    # Schema: every money column is INTEGER affinity.
    types = money_column_types(conn)
    for table, columns in MONEY_COLUMNS.items():
        assert table in types
        for col in columns:
            assert types[table][col] == "INTEGER", f"{table}.{col} must be INTEGER"

    # Parser: dollar strings become int cents; floats are rejected.
    assert dollars_to_cents("-8.00") == -800
    assert dollars_to_cents("235.00") == 23500
    assert dollars_to_cents(Decimal("64.30")) == 6430
    assert dollars_to_cents("-16.00") == -1600
    assert isinstance(dollars_to_cents("12.00"), int)

    with pytest.raises(MoneyParseError):
        dollars_to_cents(8.00)  # type: ignore[arg-type]

    with pytest.raises(MoneyParseError):
        assert_cents(12.5)  # type: ignore[arg-type]

    with pytest.raises(MoneyParseError):
        assert_cents("100")  # type: ignore[arg-type]

    # Seeded statement stores only integer cents in transactions.
    seed_statement(conn, demo_dir)
    conn.commit()
    rows = conn.execute(
        "SELECT amount_cents, typeof(amount_cents) AS t FROM transactions"
    ).fetchall()
    assert rows, "expected seeded transactions"
    for row in rows:
        assert row["t"] == "integer"
        assert isinstance(row["amount_cents"], int)

    replit = conn.execute(
        """
        SELECT amount_cents FROM transactions
        WHERE merchant_norm = 'Replit'
        """
    ).fetchone()
    assert replit is not None
    assert replit["amount_cents"] == -23500
