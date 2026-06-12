"""Reconciliation state definition for the bank-statement matching graph."""

from __future__ import annotations

import operator
from typing import Annotated, Any, NotRequired, TypedDict


class ReconciliationState(TypedDict):
    """State carried through the bank reconciliation LangGraph pipeline."""

    statement_id: str
    tenant_id: str
    exact_matched_count: NotRequired[int]
    fuzzy_matched_count: NotRequired[int]
    llm_matched_count: NotRequired[int]
    unmatched_count: NotRequired[int]
    fuzzy_candidates: NotRequired[list[dict[str, Any]]]
    unmatched_lines: NotRequired[list[dict[str, Any]]]
    report: NotRequired[dict[str, Any]]
    error: NotRequired[str]
    step_history: Annotated[list[str], operator.add]


def create_reconciliation_state(*, statement_id: str, tenant_id: str) -> ReconciliationState:
    return {
        "statement_id": statement_id,
        "tenant_id": tenant_id,
        "exact_matched_count": 0,
        "fuzzy_matched_count": 0,
        "llm_matched_count": 0,
        "unmatched_count": 0,
        "fuzzy_candidates": [],
        "unmatched_lines": [],
        "step_history": [],
    }
