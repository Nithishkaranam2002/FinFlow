"""Rule-based arithmetic checks on extracted invoice data (no LLM)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

TOLERANCE = Decimal("0.01")
# Confidence ceiling applied when the numbers on an invoice do not reconcile.
MATH_MISMATCH_CONFIDENCE_CAP = 0.5


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("$", "").strip())
    except InvalidOperation:
        return None


def _money(value: Decimal) -> str:
    return f"${value:,.2f}"


def check_invoice_math(extracted: dict[str, Any]) -> list[str]:
    """Return human-readable issues when line items, tax, freight and total do not add up.

    - Each line: quantity x unit price must equal the line amount (within 1 cent).
    - Invoice: sum of line amounts + tax + freight must equal the total (within 1 cent).
    Checks are skipped when the values needed for them were not extracted.
    """
    issues: list[str] = []
    line_items = extracted.get("line_items") or []

    line_amounts: list[Decimal] = []
    for index, line in enumerate(line_items, start=1):
        quantity = _to_decimal(line.get("quantity"))
        unit_price = _to_decimal(line.get("unit_price"))
        amount = _to_decimal(line.get("total"))
        if amount is not None:
            line_amounts.append(amount)
        if quantity is None or unit_price is None or amount is None:
            continue
        expected = quantity * unit_price
        if abs(expected - amount) > TOLERANCE:
            issues.append(
                f"Line {index} doesn't add up: {quantity.normalize():f} x {_money(unit_price)} "
                f"= {_money(expected)}, but the line says {_money(amount)}"
            )

    total = _to_decimal(extracted.get("total_amount"))
    if total is None or not line_items or len(line_amounts) != len(line_items):
        return issues

    tax = _to_decimal(extracted.get("tax_amount")) or Decimal("0")
    freight = _to_decimal(extracted.get("freight_amount")) or Decimal("0")
    computed = sum(line_amounts, Decimal("0")) + tax + freight
    if abs(computed - total) > TOLERANCE:
        extras = []
        if tax:
            extras.append(f"{_money(tax)} tax")
        if freight:
            extras.append(f"{_money(freight)} freight")
        including = f" (including {' and '.join(extras)})" if extras else ""
        issues.append(
            f"Totals don't add up: line items come to {_money(computed)}{including}, "
            f"invoice says {_money(total)}"
        )

    return issues
