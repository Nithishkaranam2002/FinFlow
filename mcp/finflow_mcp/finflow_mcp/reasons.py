"""Plain-English labels and attention reasons.

Mirrors getAttentionReasons() and the label maps in frontend/src/lib/invoiceUtils.tsx so
Claude gives the same explanations as the invoice detail page, plus the data-quality flags
that exist on seeded invoices.
"""

from __future__ import annotations

from typing import Any

STATUS_LABELS = {
    "received": "Received",
    "extracting": "Reading invoice",
    "review_required": "Review Required",
    "matched": "Matched",
    "pending_approval": "Pending Approval",
    "approved": "Approved",
    "rejected": "Rejected",
    "paid": "Paid",
}

ROLE_LABELS = {
    "ap_clerk": "AP clerk",
    "approver": "Approver",
    "controller": "Controller",
    "auditor": "Auditor",
}

FRAUD_FLAG_LABELS = {
    "THRESHOLD_GAMING": "Just under approval limit",
    "POTENTIAL_DUPLICATE": "Possible duplicate",
    "AMOUNT_ANOMALY": "Unusual amount for vendor",
    "HIGH_VELOCITY": "Many invoices in a short time",
    "BANK_ACCOUNT_RECENTLY_CHANGED": "Bank details recently changed",
    "UNKNOWN_VENDOR": "Unknown vendor",
}

# Same fields the backend weighs for overall extraction confidence.
ATTENTION_FIELD_LABELS = {
    "invoice_number": "invoice number",
    "vendor_name": "vendor name",
    "total_amount": "total amount",
    "due_date": "due date",
    "line_items": "line items",
}

OPEN_STATUSES = {"pending_approval", "review_required", "matched"}


def fraud_flag_label(flag_type: str) -> str:
    return FRAUD_FLAG_LABELS.get(flag_type, flag_type.replace("_", " ").capitalize())


def _whole_dollars(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "approval"


def describe_fraud_flag(flag: dict[str, Any]) -> str:
    flag_type = flag.get("type", "")
    description = flag.get("description", "")
    if flag_type == "THRESHOLD_GAMING":
        return (
            f"Amount is just under the {_whole_dollars(flag.get('threshold_amount'))} approval limit, "
            "a common way to avoid senior approval"
        )
    if flag_type == "POTENTIAL_DUPLICATE":
        return f"Looks like a duplicate of invoice {flag.get('matched_invoice_number') or 'already on file'}"
    if flag_type == "AMOUNT_ANOMALY":
        return f"Amount is unusual for this vendor ({description})"
    if flag_type == "HIGH_VELOCITY":
        return f"Many invoices from this vendor in a short time ({description})"
    if flag_type == "BANK_ACCOUNT_RECENTLY_CHANGED":
        return "Vendor bank details changed recently, confirm them before paying"
    if flag_type == "UNKNOWN_VENDOR":
        return "Vendor name doesn't match any known vendor"
    return description or fraud_flag_label(flag_type)


def fraud_flags(invoice: dict[str, Any]) -> list[dict[str, Any]]:
    flags = (invoice.get("flags") or {}).get("fraud_flags")
    return flags if isinstance(flags, list) else []


def has_fraud_signal(invoice: dict[str, Any]) -> bool:
    flags = invoice.get("flags") or {}
    return bool(fraud_flags(invoice) or flags.get("duplicate_of") or flags.get("threshold_avoidance"))


def attention_reasons(invoice: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    flags = invoice.get("flags") or {}

    scores = flags.get("confidence_scores") or {}
    unsure = [label for key, label in ATTENTION_FIELD_LABELS.items() if key in scores and scores[key] < 0.75]
    if unsure:
        reasons.append(f"AI was not sure about: {', '.join(unsure)}")

    reasons.extend(describe_fraud_flag(flag) for flag in fraud_flags(invoice))
    reasons.extend(issue for issue in flags.get("math_issues") or [] if isinstance(issue, str))

    # Data-quality flags carried by seeded invoices.
    if flags.get("duplicate_of"):
        reasons.append("Possible duplicate of another invoice already on file")
    if flags.get("threshold_avoidance"):
        reasons.append("Amount looks set to stay under an approval limit")
    if flags.get("vendor_name_misspelled"):
        reasons.append("Vendor name on the invoice looks misspelled")
    if flags.get("amount_as_text"):
        reasons.append("Amount was written in words, check it was read correctly")
    if flags.get("missing_due_date"):
        reasons.append("Due date is missing")
    if flags.get("stale_recovery"):
        reasons.append("Processing stalled and was recovered, needs a manual check")

    if invoice.get("status") in OPEN_STATUSES and flags.get("required_role") == "controller":
        escalated = any(flag.get("severity") in {"HIGH", "CRITICAL"} for flag in fraud_flags(invoice))
        reasons.append(
            "Needs controller approval: a fraud check flagged this invoice"
            if escalated
            else "Needs controller approval: amount is above the approver limit"
        )

    if not reasons and invoice.get("status") == "review_required":
        reasons.append(str(flags.get("review_reason") or "Flagged for manual review"))

    return reasons
