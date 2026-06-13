"""Fraud detection rules for invoice processing."""

from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.invoice import Invoice
from models.tenant import Tenant
from models.vendor import Vendor

SEVERITY_WEIGHTS = {
    "CRITICAL": 0.8,
    "HIGH": 0.5,
    "MEDIUM": 0.3,
}

DEFAULT_THRESHOLDS = {
    "manager": Decimal("5000"),
    "director": Decimal("25000"),
}


@dataclass
class FraudDetectionResult:
    fraud_flags: list[dict[str, Any]] = field(default_factory=list)
    overall_risk_score: float = 0.0
    requires_human_review: bool = False
    approval_status: str | None = None


def calculate_risk_score(fraud_flags: list[dict[str, Any]]) -> float:
    score = sum(SEVERITY_WEIGHTS.get(flag.get("severity", "MEDIUM"), 0.3) for flag in fraud_flags)
    return round(min(score, 1.0), 4)


def get_tenant_thresholds(tenant_config: dict[str, Any]) -> dict[str, Decimal]:
    thresholds = tenant_config.get("approval_thresholds", {})
    manager = thresholds.get("manager", tenant_config.get("approval_threshold", "5000"))
    director = thresholds.get("director", "25000")
    return {
        "manager": Decimal(str(manager)),
        "director": Decimal(str(director)),
    }


def amounts_within_one_percent(left: Decimal, right: Decimal) -> bool:
    if right == 0:
        return left == 0
    return abs(left - right) / abs(right) <= Decimal("0.01")


def is_within_threshold_gaming(amount: Decimal, threshold: Decimal, margin: Decimal = Decimal("0.05")) -> bool:
    lower_bound = threshold * (Decimal("1") - margin)
    return lower_bound <= amount < threshold


def _invoice_date(invoice: Invoice) -> date | None:
    extracted = invoice.extracted_data or {}
    raw_date = extracted.get("invoice_date")
    if raw_date:
        return date.fromisoformat(str(raw_date))
    created = invoice.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created.date()


async def run_fraud_checks(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    vendor_id: uuid.UUID | None,
    invoice_number: str,
    amount: Decimal,
    invoice_date: date | None,
    existing_flags: list[dict[str, Any]] | None = None,
) -> FraudDetectionResult:
    flags = list(existing_flags or [])

    tenant = await db.get(Tenant, tenant_id)
    tenant_config = tenant.config if tenant else {}
    thresholds = get_tenant_thresholds(tenant_config)

    if vendor_id:
        flags.extend(
            await _check_duplicates(
                db,
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                vendor_id=vendor_id,
                amount=amount,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
            )
        )
        flags.extend(
            await _check_amount_anomaly(
                db,
                tenant_id=tenant_id,
                vendor_id=vendor_id,
                invoice_id=invoice_id,
                amount=amount,
            )
        )
        flags.extend(
            await _check_high_velocity(
                db,
                tenant_id=tenant_id,
                vendor_id=vendor_id,
                invoice_id=invoice_id,
                amount=amount,
            )
        )

    flags.extend(_check_threshold_gaming(amount, thresholds))

    risk_score = calculate_risk_score(flags)
    result = FraudDetectionResult(
        fraud_flags=flags,
        overall_risk_score=risk_score,
    )

    if risk_score > 0.7:
        result.requires_human_review = True

    return result


async def _check_duplicates(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    vendor_id: uuid.UUID,
    amount: Decimal,
    invoice_number: str,
    invoice_date: date | None,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    window_start = datetime.now(timezone.utc) - timedelta(days=30)

    result = await db.execute(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.vendor_id == vendor_id,
            Invoice.id != invoice_id,
            Invoice.created_at >= window_start,
        )
    )
    candidates = result.scalars().all()
    reference_date = invoice_date or datetime.now(timezone.utc).date()

    for candidate in candidates:
        if not amounts_within_one_percent(amount, candidate.amount):
            continue

        candidate_date = _invoice_date(candidate)
        if candidate_date and reference_date:
            if abs((candidate_date - reference_date).days) > 30:
                continue

        similarity = fuzz.ratio(invoice_number, candidate.invoice_number)
        if similarity > 80:
            flags.append(
                {
                    "type": "POTENTIAL_DUPLICATE",
                    "severity": "CRITICAL",
                    "description": (
                        f"Potential duplicate of invoice {candidate.invoice_number} "
                        f"({similarity:.0f}% number similarity, amount within 1%)"
                    ),
                    "matched_invoice_id": str(candidate.id),
                    "matched_invoice_number": candidate.invoice_number,
                    "similarity_score": similarity,
                }
            )
            break

    return flags


def _check_threshold_gaming(
    amount: Decimal,
    thresholds: dict[str, Decimal],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    for role, threshold in thresholds.items():
        if is_within_threshold_gaming(amount, threshold):
            flags.append(
                {
                    "type": "THRESHOLD_GAMING",
                    "severity": "HIGH",
                    "description": (
                        f"Amount ${amount} is within 5% below the {role} "
                        f"approval threshold of ${threshold}"
                    ),
                    "threshold_role": role,
                    "threshold_amount": str(threshold),
                    "invoice_amount": str(amount),
                }
            )
    return flags


async def _check_amount_anomaly(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    invoice_id: uuid.UUID,
    amount: Decimal,
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(Invoice.amount)
        .where(
            Invoice.tenant_id == tenant_id,
            Invoice.vendor_id == vendor_id,
            Invoice.id != invoice_id,
        )
        .order_by(Invoice.created_at.desc())
        .limit(12)
    )
    historical = [Decimal(str(row[0])) for row in result.all()]
    if len(historical) < 3:
        return []

    mean = Decimal(str(statistics.mean(historical)))
    stdev = Decimal(str(statistics.pstdev(historical)))
    if stdev == 0:
        return []

    z_distance = abs(amount - mean) / stdev
    if z_distance <= Decimal("2.5"):
        return []

    lower = mean - (Decimal("2.5") * stdev)
    upper = mean + (Decimal("2.5") * stdev)
    return [
        {
            "type": "AMOUNT_ANOMALY",
            "severity": "MEDIUM",
            "description": (
                f"Expected range: ${lower:.2f}-${upper:.2f}, Got: ${amount:.2f}"
            ),
            "mean_amount": str(mean),
            "stdev_amount": str(stdev),
            "z_score": float(z_distance),
        }
    ]


async def _check_high_velocity(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    vendor_id: uuid.UUID,
    invoice_id: uuid.UUID,
    amount: Decimal,
) -> list[dict[str, Any]]:
    window_start = datetime.now(timezone.utc) - timedelta(days=7)
    result = await db.execute(
        select(Invoice).where(
            Invoice.tenant_id == tenant_id,
            Invoice.vendor_id == vendor_id,
            Invoice.created_at >= window_start,
        )
    )
    recent = list(result.scalars().all())
    count = len(recent)
    total = sum((invoice.amount for invoice in recent), Decimal("0"))

    if not any(invoice.id == invoice_id for invoice in recent):
        count += 1
        total += amount

    if count <= 3:
        return []

    total = sum((invoice.amount for invoice in recent), Decimal("0"))
    if total <= Decimal("10000"):
        return []

    return [
        {
            "type": "HIGH_VELOCITY",
            "severity": "MEDIUM",
            "description": (
                f"{count} invoices from vendor in last 7 days totaling ${total:.2f}"
            ),
            "invoice_count_7d": count,
            "total_amount_7d": str(total),
        }
    ]
