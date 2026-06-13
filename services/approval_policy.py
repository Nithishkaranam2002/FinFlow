"""Approval policy resolution and role checks."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from models.user import User, UserRole

AUTO_APPROVE_LIMIT = Decimal("1000")
AP_CLERK_LIMIT = Decimal("5000")
CONTROLLER_LIMIT = Decimal("25000")
HIGH_SEVERITIES = {"HIGH", "CRITICAL"}


def resolve_required_role(
    amount: Decimal,
    fraud_flags: list[dict[str, Any]] | None,
    tenant_config: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    """
    Returns (required_role, auto_approve).

    Policy:
    - under $1,000: auto_approve
    - $1,000 to $5,000: ap_clerk
    - $5,000 to $25,000: approver
    - over $25,000: controller
    - HIGH/CRITICAL fraud flags: always controller
    """
    config = tenant_config or {}
    thresholds = config.get("approval_thresholds", {})
    auto_limit = Decimal(str(thresholds.get("auto_approve", AUTO_APPROVE_LIMIT)))
    clerk_limit = Decimal(str(thresholds.get("ap_clerk", AP_CLERK_LIMIT)))
    controller_limit = Decimal(str(thresholds.get("controller", CONTROLLER_LIMIT)))

    if config.get("approval_threshold") is not None:
        clerk_limit = Decimal(str(config["approval_threshold"]))

    policy_rules = config.get("policy_rules") or {}
    if policy_rules.get("require_dual_approval_above") is not None:
        controller_limit = Decimal(str(policy_rules["require_dual_approval_above"]))

    if fraud_flags and any(flag.get("severity") in HIGH_SEVERITIES for flag in fraud_flags):
        return UserRole.CONTROLLER.value, False

    if amount < auto_limit:
        return UserRole.AP_CLERK.value, True
    if amount < clerk_limit:
        return UserRole.AP_CLERK.value, False
    if amount < controller_limit:
        return UserRole.APPROVER.value, False
    return UserRole.CONTROLLER.value, False


def user_can_approve(user: User, required_role: str) -> bool:
    from core.rbac import user_meets_required_role

    return user_meets_required_role(user, required_role)
