"""Parse bank statement CSV and MT940 files."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

DESCRIPTION_COLUMNS = {
    "description",
    "narrative",
    "details",
    "memo",
    "particulars",
    "transaction description",
    "txn description",
    "remarks",
    "narration",
}

DATE_COLUMNS = {
    "date",
    "transaction date",
    "txn date",
    "value date",
    "posting date",
    "transaction_date",
}

STATEMENT_DATE_COLUMNS = {"statement date", "statement_date", "period end"}

AMOUNT_COLUMNS = {
    "amount",
    "debit",
    "credit",
    "transaction amount",
    "txn amount",
    "withdrawal",
    "deposit",
}

REFERENCE_COLUMNS = {
    "reference",
    "ref",
    "cheque no",
    "check no",
    "utr",
    "transaction id",
    "txn id",
    "bank ref",
}

CURRENCY_COLUMNS = {"currency", "ccy", "curr"}

BANK_TXN_ID_COLUMNS = {
    "bank transaction id",
    "transaction id",
    "txn id",
    "bank_transaction_id",
    "unique id",
}

SMART_QUOTE_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\ufeff": "",
    }
)

MOJIBAKE_PATTERNS = [
    (r"Ã¢â‚¬â„¢", "'"),
    (r"Ã¢â‚¬Å“", '"'),
    (r"â€™", "'"),
    (r"â€œ", '"'),
    (r"Â ", " "),
    (r"\xe2\x80\x93", "-"),
    (r"\xe2\x80\x94", "-"),
]


@dataclass
class ParsedStatementLine:
    statement_date: date | None
    transaction_date: date
    description: str
    amount: Decimal
    reference: str | None
    bank_transaction_id: str | None
    currency: str


def clean_description(text: str) -> str:
    """Normalize bank description text for Indian/international statement quality issues."""
    if not text:
        return ""

    cleaned = text.translate(SMART_QUOTE_MAP)
    for pattern, replacement in MOJIBAKE_PATTERNS:
        cleaned = re.sub(pattern, replacement, cleaned)

    cleaned = unicodedata.normalize("NFKC", cleaned)
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def normalize_amount(raw: str | Decimal | float | int | None) -> Decimal:
    if raw is None or raw == "":
        return Decimal("0")

    if isinstance(raw, Decimal):
        return raw

    text = str(raw).strip()
    if not text:
        return Decimal("0")

    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]

    text = text.replace(",", "").replace("₹", "").replace("INR", "").strip()
    if text.startswith("-"):
        negative = True
        text = text[1:].strip()
    elif text.startswith("+"):
        text = text[1:].strip()
    if text.endswith("DR") or text.endswith("Dr"):
        negative = True
        text = text[:-2].strip()
    elif text.endswith("CR") or text.endswith("Cr"):
        text = text[:-2].strip()

    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Unable to parse amount: {raw}") from exc

    return -value if negative else value


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None

    text = str(value).strip()
    formats = (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%b-%Y",
        "%d %b %Y",
        "%Y/%m/%d",
        "%d.%m.%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_header(header: str) -> str:
    return re.sub(r"[\s_]+", " ", header.strip().lower())


def _pick_column(headers: dict[str, str], candidates: set[str]) -> str | None:
    for normalized, original in headers.items():
        if normalized in candidates:
            return original
    for normalized, original in headers.items():
        if any(candidate in normalized for candidate in candidates):
            return original
    return None


def parse_csv_statement(content: bytes, *, default_currency: str = "USD") -> list[ParsedStatementLine]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV file has no header row")

    headers = {_normalize_header(name): name for name in reader.fieldnames}
    description_col = _pick_column(headers, DESCRIPTION_COLUMNS)
    date_col = _pick_column(headers, DATE_COLUMNS)
    statement_date_col = _pick_column(headers, STATEMENT_DATE_COLUMNS)
    amount_col = _pick_column(headers, AMOUNT_COLUMNS)
    debit_col = _pick_column(headers, {"debit", "withdrawal"})
    credit_col = _pick_column(headers, {"credit", "deposit"})
    reference_col = _pick_column(headers, REFERENCE_COLUMNS)
    currency_col = _pick_column(headers, CURRENCY_COLUMNS)
    bank_txn_col = _pick_column(headers, BANK_TXN_ID_COLUMNS)

    if not description_col or not date_col:
        raise ValueError("CSV must include description and date columns")

    lines: list[ParsedStatementLine] = []
    for row in reader:
        description = clean_description(row.get(description_col, ""))
        if not description:
            continue

        txn_date = _parse_date(row.get(date_col))
        if txn_date is None:
            continue

        if amount_col:
            amount = normalize_amount(row.get(amount_col))
        elif debit_col or credit_col:
            debit = normalize_amount(row.get(debit_col)) if debit_col else Decimal("0")
            credit = normalize_amount(row.get(credit_col)) if credit_col else Decimal("0")
            amount = credit - abs(debit)
        else:
            raise ValueError("CSV must include amount, or debit/credit columns")

        currency = (row.get(currency_col) or default_currency).upper()[:3]
        reference = clean_description(row.get(reference_col, "") or "") or None
        bank_txn_id = (row.get(bank_txn_col) or "").strip() or None
        statement_date = _parse_date(row.get(statement_date_col)) if statement_date_col else None

        lines.append(
            ParsedStatementLine(
                statement_date=statement_date,
                transaction_date=txn_date,
                description=description,
                amount=amount,
                reference=reference[:256] if reference else None,
                bank_transaction_id=bank_txn_id[:128] if bank_txn_id else None,
                currency=currency,
            )
        )

    logger.info("csv_statement_parsed", line_count=len(lines))
    return lines


def parse_mt940_statement(content: bytes, *, default_currency: str = "USD") -> list[ParsedStatementLine]:
    text = content.decode("utf-8", errors="replace")
    lines: list[ParsedStatementLine] = []
    statement_date: date | None = None
    currency = default_currency

    currency_match = re.search(r":60[FM]:[CD](\d{6})([A-Z]{3})", text)
    if currency_match:
        currency = currency_match.group(2)

    statement_date_match = re.search(r":62[FM]:[CD]\d{6}(\d{6})", text)
    if statement_date_match:
        statement_date = _parse_mt940_date(statement_date_match.group(1))

    for block in re.finditer(
        r":61:(?P<line>[^\n:]+)(?:\n(?::86:(?P<narrative>[^\n:]+))?)?",
        text,
    ):
        txn_line = block.group("line")
        narrative = clean_description(block.group("narrative") or "")
        parsed = _parse_mt940_transaction(txn_line, narrative, currency, statement_date)
        if parsed:
            lines.append(parsed)

    logger.info("mt940_statement_parsed", line_count=len(lines))
    return lines


def _parse_mt940_date(value: str) -> date | None:
    if len(value) != 6 or not value.isdigit():
        return None
    year = 2000 + int(value[:2])
    month = int(value[2:4])
    day = int(value[4:6])
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_mt940_transaction(
    txn_line: str,
    narrative: str,
    currency: str,
    statement_date: date | None,
) -> ParsedStatementLine | None:
    match = re.match(
        r"(?P<date>\d{6})(?P<dc>[CD])(?P<amount>[0-9,]+(?:,\d{0,2})?)"
        r"(?P<type>[A-Z]{4})(?P<reference>[^\n//]*)",
        txn_line.strip(),
    )
    if not match:
        return None

    txn_date = _parse_mt940_date(match.group("date"))
    if txn_date is None:
        return None

    raw_amount = match.group("amount").replace(",", ".")
    amount = normalize_amount(raw_amount)
    if match.group("dc") == "D":
        amount = -abs(amount)

    reference = clean_description(match.group("reference") or "") or None
    description = narrative or reference or f"MT940 {match.group('type')} transaction"

    return ParsedStatementLine(
        statement_date=statement_date,
        transaction_date=txn_date,
        description=clean_description(description),
        amount=amount,
        reference=reference[:256] if reference else None,
        bank_transaction_id=reference[:128] if reference else None,
        currency=currency,
    )


def parse_statement_file(
    content: bytes,
    filename: str,
    *,
    default_currency: str = "USD",
) -> tuple[str, list[ParsedStatementLine]]:
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        return "csv", parse_csv_statement(content, default_currency=default_currency)
    if lower_name.endswith(".mt940") or lower_name.endswith(".sta") or lower_name.endswith(".940"):
        return "mt940", parse_mt940_statement(content, default_currency=default_currency)

    # Attempt CSV first, then MT940 based on content markers.
    if content.strip().startswith(b":20:") or b":61:" in content:
        return "mt940", parse_mt940_statement(content, default_currency=default_currency)
    return "csv", parse_csv_statement(content, default_currency=default_currency)
