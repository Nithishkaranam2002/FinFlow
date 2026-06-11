"""Vendor name matching utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from rapidfuzz import fuzz, process

from models.vendor import Vendor

MATCH_CONFIDENT_THRESHOLD = 85
MATCH_AMBIGUOUS_THRESHOLD = 65
BANK_ACCOUNT_RECENT_DAYS = 7


@dataclass
class VendorMatchResult:
    vendor_match: dict | None
    match_confidence: float | None
    requires_human_review: bool
    review_reason: str
    fraud_flags: list[dict]
    matched_vendor: Vendor | None


def match_vendor_by_name(
    extracted_vendor_name: str,
    vendors: list[Vendor],
) -> VendorMatchResult:
    if not extracted_vendor_name or not vendors:
        return VendorMatchResult(
            vendor_match=None,
            match_confidence=None,
            requires_human_review=False,
            review_reason="",
            fraud_flags=[
                {
                    "type": "UNKNOWN_VENDOR",
                    "severity": "HIGH",
                    "description": "No vendor candidates available for matching",
                }
            ],
            matched_vendor=None,
        )

    vendor_names = [vendor.name for vendor in vendors]
    result = process.extractOne(
        extracted_vendor_name,
        vendor_names,
        scorer=fuzz.token_sort_ratio,
    )

    if result is None:
        return VendorMatchResult(
            vendor_match=None,
            match_confidence=0.0,
            requires_human_review=False,
            review_reason="",
            fraud_flags=[
                {
                    "type": "UNKNOWN_VENDOR",
                    "severity": "HIGH",
                    "description": f"No match found for vendor '{extracted_vendor_name}'",
                }
            ],
            matched_vendor=None,
        )

    matched_name, score, index = result
    vendor = vendors[index]
    fraud_flags: list[dict] = []

    if vendor.bank_account_changed_at:
        changed_at = vendor.bank_account_changed_at
        if changed_at.tzinfo is None:
            changed_at = changed_at.replace(tzinfo=timezone.utc)
        days_since_change = (datetime.now(timezone.utc) - changed_at).days
        if days_since_change <= BANK_ACCOUNT_RECENT_DAYS:
            fraud_flags.append(
                {
                    "type": "BANK_ACCOUNT_RECENTLY_CHANGED",
                    "severity": "HIGH",
                    "description": (
                        f"Vendor '{vendor.name}' bank account changed "
                        f"{days_since_change} day(s) ago"
                    ),
                    "vendor_id": str(vendor.id),
                    "bank_account_changed_at": changed_at.isoformat(),
                }
            )

    if score >= MATCH_CONFIDENT_THRESHOLD:
        return VendorMatchResult(
            vendor_match={
                "vendor_id": str(vendor.id),
                "matched_name": vendor.name,
                "extracted_name": extracted_vendor_name,
                "match_confidence": score,
                "match_method": "rapidfuzz_token_sort_ratio",
                "email": vendor.email,
                "payment_terms_days": vendor.payment_terms_days,
            },
            match_confidence=score,
            requires_human_review=False,
            review_reason="",
            fraud_flags=fraud_flags,
            matched_vendor=vendor,
        )

    if score >= MATCH_AMBIGUOUS_THRESHOLD:
        return VendorMatchResult(
            vendor_match={
                "vendor_id": str(vendor.id),
                "matched_name": vendor.name,
                "extracted_name": extracted_vendor_name,
                "match_confidence": score,
                "match_method": "rapidfuzz_token_sort_ratio",
                "email": vendor.email,
                "payment_terms_days": vendor.payment_terms_days,
            },
            match_confidence=score,
            requires_human_review=True,
            review_reason=(
                f"Ambiguous vendor match: extracted '{extracted_vendor_name}' "
                f"matched '{vendor.name}' with {score:.0f}% confidence"
            ),
            fraud_flags=fraud_flags,
            matched_vendor=vendor,
        )

    return VendorMatchResult(
        vendor_match=None,
        match_confidence=score,
        requires_human_review=False,
        review_reason="",
        fraud_flags=[
            *fraud_flags,
            {
                "type": "UNKNOWN_VENDOR",
                "severity": "HIGH",
                "description": (
                    f"Extracted vendor '{extracted_vendor_name}' best match "
                    f"'{matched_name}' only scored {score:.0f}%"
                ),
            },
        ],
        matched_vendor=None,
    )
