"""Central LiteLLM gateway with routing, cost tracking, and semantic cache."""

from __future__ import annotations

import hashlib
import json
import math
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

import litellm
import structlog
from langchain_core.messages import BaseMessage
from litellm import Router
from sqlalchemy import func, select

from core.config import Settings, get_settings
from core.database import async_session_factory
from core.redis import get_redis_client
from models.invoice import Invoice
from models.llm_log import LLMCallLog

logger = structlog.get_logger(__name__)

TIER_FAST = "fast"
TIER_STANDARD = "standard"
TIER_PREMIUM = "premium"

# OpenAI-only model tiers (override via PRIMARY_MODEL / STANDARD_MODEL / PREMIUM_MODEL in .env)
FAST_MODEL = "gpt-4o-mini"
STANDARD_MODEL = "gpt-4o-mini"
PREMIUM_MODEL = "gpt-4o"
VISION_MODEL = PREMIUM_MODEL  # vision extraction always uses gpt-4o

SEMANTIC_CACHE_THRESHOLD = 0.97
SEMANTIC_CACHE_TTL_SECONDS = 60 * 60 * 24 * 30
EMBEDDING_MODEL = "text-embedding-3-small"


@dataclass
class LLMResponse:
    content: str
    model: str
    tier: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    cache_hit: bool = False
    extraction_prior: dict[str, Any] | None = None


def route_by_complexity(task_type: str, context: dict[str, Any]) -> str:
    """
    Return LiteLLM router tier alias: fast | standard | premium.

    Rules:
    - vision_extraction or is_vision -> premium (gpt-4o)
    - extraction with known vendor confidence > 0.9 -> fast (gpt-4o-mini)
    - first-time vendor extraction -> standard (gpt-4o-mini)
    - fraud_judgment, reconciliation_llm_pass, risk_score > 0.5 -> premium (gpt-4o)
    """
    risk_score = float(context.get("risk_score") or context.get("overall_risk_score") or 0.0)
    if task_type in {"fraud_judgment", "reconciliation_llm_pass"} or risk_score > 0.5:
        return TIER_PREMIUM

    if task_type == "vision_extraction" or context.get("is_vision"):
        return TIER_PREMIUM

    if task_type in {"extraction"}:
        vendor_confidence = float(context.get("vendor_confidence_hint") or 0.0)
        if vendor_confidence > 0.9 and context.get("known_vendor"):
            return TIER_FAST
        return TIER_STANDARD

    if task_type in {"payment_memo", "simple_extraction"}:
        return TIER_FAST

    return TIER_STANDARD


def _build_model_list(settings: Settings) -> list[dict[str, Any]]:
    openai_key = settings.openai_api_key or None

    def entry(tier: str, model: str) -> dict[str, Any]:
        params: dict[str, Any] = {"model": model}
        if openai_key:
            params["api_key"] = openai_key
        return {"model_name": tier, "litellm_params": params}

    return [
        entry(TIER_FAST, settings.primary_model or FAST_MODEL),
        entry(TIER_STANDARD, settings.standard_model or STANDARD_MODEL),
        entry(TIER_PREMIUM, settings.premium_model or PREMIUM_MODEL),
    ]


def _build_router(settings: Settings) -> Router:
    # Anthropic fallback chain (re-enable when ANTHROPIC_API_KEY is set):
    #   anthropic_key = settings.anthropic_api_key or None
    #   def anthropic_entry(tier: str, model: str) -> dict:
    #       return {"model_name": tier, "litellm_params": {
    #           "model": f"anthropic/{model}", "api_key": anthropic_key}}
    #   fallbacks = [
    #       {TIER_FAST: ["fast-fallback"]},
    #       {TIER_STANDARD: ["standard-fallback"]},
    #       {TIER_PREMIUM: ["premium-fallback"]},
    #   ]
    #   model_list = [
    #       anthropic_entry(TIER_FAST, "claude-3-5-haiku-20241022"),
    #       entry("fast-fallback", "gpt-4o-mini"),
    #       ...
    #   ]
    return Router(
        model_list=_build_model_list(settings),
        num_retries=2,
        timeout=120,
    )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _to_litellm_messages(messages: list[Any]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, dict):
            converted.append(message)
            continue
        if isinstance(message, BaseMessage):
            role = message.type
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            content = message.content
            if isinstance(content, list):
                converted.append({"role": role, "content": content})
            else:
                converted.append({"role": role, "content": str(content)})
            continue
        converted.append({"role": "user", "content": str(message)})
    return converted


class SemanticCache:
    """Redis-backed semantic cache for vendor document extraction patterns."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _cache_key(self, tenant_id: str, vendor_id: str) -> str:
        return f"finflow:semantic_cache:{tenant_id}:{vendor_id}"

    async def _embed(self, text: str) -> list[float]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self.settings.openai_api_key or None)
        response = await client.embeddings.create(model=EMBEDDING_MODEL, input=text[:8000])
        return response.data[0].embedding

    def _document_fingerprint(self, document_bytes: bytes, vendor_id: str | None) -> str:
        digest = hashlib.sha256(document_bytes).hexdigest()
        return f"vendor:{vendor_id or 'unknown'}|bytes:{len(document_bytes)}|sha256:{digest}"

    async def lookup(
        self,
        *,
        tenant_id: str,
        vendor_id: str | None,
        document_bytes: bytes,
    ) -> dict[str, Any] | None:
        if not vendor_id:
            return None

        redis = get_redis_client()
        key = self._cache_key(tenant_id, vendor_id)
        entries_raw = await redis.lrange(key, 0, -1)
        if not entries_raw:
            return None

        query_embedding = await self._embed(self._document_fingerprint(document_bytes, vendor_id))
        best_score = 0.0
        best_entry: dict[str, Any] | None = None

        for raw in entries_raw:
            entry = json.loads(raw)
            score = _cosine_similarity(query_embedding, entry.get("embedding", []))
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry and best_score >= SEMANTIC_CACHE_THRESHOLD:
            logger.info(
                "semantic_cache_hit",
                tenant_id=tenant_id,
                vendor_id=vendor_id,
                similarity=round(best_score, 4),
            )
            return {
                "similarity": best_score,
                "extraction_pattern": best_entry.get("extraction_pattern"),
                "confidence_boost": best_entry.get("confidence_boost", 0.05),
            }
        return None

    async def store(
        self,
        *,
        tenant_id: str,
        vendor_id: str,
        document_bytes: bytes,
        extraction_pattern: dict[str, Any],
        confidence_boost: float = 0.05,
    ) -> None:
        redis = get_redis_client()
        key = self._cache_key(tenant_id, vendor_id)
        embedding = await self._embed(self._document_fingerprint(document_bytes, vendor_id))
        payload = json.dumps(
            {
                "embedding": embedding,
                "extraction_pattern": extraction_pattern,
                "confidence_boost": confidence_boost,
                "stored_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        await redis.lpush(key, payload)
        await redis.ltrim(key, 0, 49)
        await redis.expire(key, SEMANTIC_CACHE_TTL_SECONDS)


class CostTracker:
    """Persist and summarize LLM usage costs per tenant."""

    async def record(
        self,
        *,
        tenant_id: str,
        agent_name: str,
        task_type: str,
        tier: str,
        model_used: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        invoice_id: str | None = None,
        cache_hit: bool = False,
    ) -> None:
        async with async_session_factory() as db:
            db.add(
                LLMCallLog(
                    tenant_id=uuid.UUID(tenant_id),
                    agent_name=agent_name,
                    task_type=task_type,
                    tier=tier,
                    model_used=model_used,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    invoice_id=uuid.UUID(invoice_id) if invoice_id else None,
                    cache_hit=cache_hit,
                )
            )
            await db.commit()

    async def get_cost_summary(
        self,
        tenant_id: uuid.UUID,
        date_range: tuple[date, date],
    ) -> dict[str, Any]:
        start_dt = datetime.combine(date_range[0], datetime.min.time(), tzinfo=timezone.utc)
        end_dt = datetime.combine(date_range[1] + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)

        async with async_session_factory() as db:
            total_result = await db.execute(
                select(
                    func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0),
                    func.count(),
                    func.coalesce(func.sum(LLMCallLog.input_tokens), 0),
                    func.coalesce(func.sum(LLMCallLog.output_tokens), 0),
                ).where(
                    LLMCallLog.tenant_id == tenant_id,
                    LLMCallLog.created_at >= start_dt,
                    LLMCallLog.created_at < end_dt,
                )
            )
            total_cost, call_count, input_tokens, output_tokens = total_result.one()

            by_model_result = await db.execute(
                select(
                    LLMCallLog.model_used,
                    func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0),
                    func.count(),
                )
                .where(
                    LLMCallLog.tenant_id == tenant_id,
                    LLMCallLog.created_at >= start_dt,
                    LLMCallLog.created_at < end_dt,
                )
                .group_by(LLMCallLog.model_used)
                .order_by(func.sum(LLMCallLog.cost_usd).desc())
            )
            cost_by_model = [
                {"model": model, "cost_usd": float(cost), "calls": calls}
                for model, cost, calls in by_model_result.all()
            ]

            by_agent_result = await db.execute(
                select(
                    LLMCallLog.agent_name,
                    func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0),
                    func.count(),
                )
                .where(
                    LLMCallLog.tenant_id == tenant_id,
                    LLMCallLog.created_at >= start_dt,
                    LLMCallLog.created_at < end_dt,
                )
                .group_by(LLMCallLog.agent_name)
                .order_by(func.sum(LLMCallLog.cost_usd).desc())
            )
            cost_by_agent = [
                {"agent": agent, "cost_usd": float(cost), "calls": calls}
                for agent, cost, calls in by_agent_result.all()
            ]

            by_day_result = await db.execute(
                select(
                    func.date(LLMCallLog.created_at).label("day"),
                    func.coalesce(func.sum(LLMCallLog.cost_usd), 0.0),
                    func.count(),
                )
                .where(
                    LLMCallLog.tenant_id == tenant_id,
                    LLMCallLog.created_at >= start_dt,
                    LLMCallLog.created_at < end_dt,
                )
                .group_by(func.date(LLMCallLog.created_at))
                .order_by(func.date(LLMCallLog.created_at))
            )
            cost_by_day = [
                {"date": day.isoformat(), "cost_usd": float(cost), "calls": calls}
                for day, cost, calls in by_day_result.all()
            ]

            invoice_count_result = await db.execute(
                select(func.count(func.distinct(Invoice.id))).where(
                    Invoice.tenant_id == tenant_id,
                    Invoice.created_at >= start_dt,
                    Invoice.created_at < end_dt,
                )
            )
            invoice_count = invoice_count_result.scalar_one() or 0

        total_cost_f = float(total_cost or 0.0)
        return {
            "total_cost_usd": round(total_cost_f, 6),
            "total_calls": int(call_count or 0),
            "total_input_tokens": int(input_tokens or 0),
            "total_output_tokens": int(output_tokens or 0),
            "cost_by_model": cost_by_model,
            "cost_by_agent": cost_by_agent,
            "cost_by_day": cost_by_day,
            "average_cost_per_invoice_usd": round(
                total_cost_f / invoice_count, 6
            )
            if invoice_count
            else 0.0,
            "invoice_count": invoice_count,
        }


async def _mem0_vendor_confidence(tenant_id: str, vendor_id: str | None) -> float | None:
    settings = get_settings()
    if not settings.mem0_api_key or not vendor_id:
        return None
    try:
        from mem0 import MemoryClient

        client = MemoryClient(api_key=settings.mem0_api_key)
        memories = client.search(
            query=f"vendor extraction confidence for vendor {vendor_id}",
            user_id=f"{tenant_id}:{vendor_id}",
            limit=3,
        )
        for item in memories or []:
            metadata = item.get("metadata") or {}
            confidence = metadata.get("extraction_confidence") or metadata.get("confidence")
            if confidence is not None:
                return float(confidence)
    except Exception:
        logger.warning("mem0_vendor_lookup_failed", tenant_id=tenant_id, vendor_id=vendor_id)
    return None


async def _db_vendor_confidence(tenant_id: str, vendor_id: str | None) -> float | None:
    if not vendor_id:
        return None
    async with async_session_factory() as db:
        result = await db.execute(
            select(func.avg(Invoice.extraction_confidence), func.count())
            .where(
                Invoice.tenant_id == uuid.UUID(tenant_id),
                Invoice.vendor_id == uuid.UUID(vendor_id),
                Invoice.extraction_confidence.is_not(None),
            )
        )
        avg_confidence, count = result.one()
        if count and avg_confidence is not None:
            return float(avg_confidence)
    return None


async def build_routing_context(
    *,
    tenant_id: str,
    vendor_id: str | None = None,
    is_vision: bool = False,
    risk_score: float = 0.0,
) -> dict[str, Any]:
    mem0_confidence = await _mem0_vendor_confidence(tenant_id, vendor_id)
    db_confidence = await _db_vendor_confidence(tenant_id, vendor_id)
    vendor_confidence = mem0_confidence if mem0_confidence is not None else (db_confidence or 0.0)
    known_vendor = vendor_confidence > 0.0
    first_time_vendor = not known_vendor

    return {
        "tenant_id": tenant_id,
        "vendor_id": vendor_id,
        "is_vision": is_vision,
        "risk_score": risk_score,
        "known_vendor": known_vendor,
        "first_time_vendor": first_time_vendor,
        "vendor_confidence_hint": vendor_confidence,
    }


class LLMGateway:
    """Unified async entrypoint for all FinFlow LLM calls."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.router = _build_router(self.settings)
        self.cost_tracker = CostTracker()
        self.semantic_cache = SemanticCache(self.settings)

    async def acompletion(
        self,
        *,
        messages: list[Any],
        task_type: str,
        agent_name: str,
        tenant_id: str,
        context: dict[str, Any] | None = None,
        invoice_id: str | None = None,
        tier: str | None = None,
    ) -> LLMResponse:
        routing_context = context or {}
        selected_tier = tier or route_by_complexity(task_type, routing_context)
        litellm_messages = _to_litellm_messages(messages)

        started = time.perf_counter()
        response = await self.router.acompletion(
            model=selected_tier,
            messages=litellm_messages,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        model_used = getattr(response, "model", selected_tier)

        try:
            cost_usd = float(
                litellm.completion_cost(completion_response=response) or 0.0
            )
        except Exception:
            cost_usd = 0.0

        await self.cost_tracker.record(
            tenant_id=tenant_id,
            agent_name=agent_name,
            task_type=task_type,
            tier=selected_tier,
            model_used=model_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            invoice_id=invoice_id,
        )

        logger.info(
            "llm_gateway_call",
            agent=agent_name,
            task_type=task_type,
            tier=selected_tier,
            model=model_used,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

        return LLMResponse(
            content=content,
            model=model_used,
            tier=selected_tier,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

    async def acompletion_with_semantic_cache(
        self,
        *,
        messages: list[Any],
        task_type: str,
        agent_name: str,
        tenant_id: str,
        vendor_id: str | None,
        document_bytes: bytes,
        context: dict[str, Any] | None = None,
        invoice_id: str | None = None,
    ) -> LLMResponse:
        cache_hit = await self.semantic_cache.lookup(
            tenant_id=tenant_id,
            vendor_id=vendor_id,
            document_bytes=document_bytes,
        )

        routing_context = dict(context or {})
        if cache_hit:
            routing_context["vendor_confidence_hint"] = max(
                float(routing_context.get("vendor_confidence_hint") or 0.0),
                0.95,
            )
            routing_context["known_vendor"] = True

        response = await self.acompletion(
            messages=messages,
            task_type=task_type,
            agent_name=agent_name,
            tenant_id=tenant_id,
            context=routing_context,
            invoice_id=invoice_id,
        )
        response.extraction_prior = cache_hit.get("extraction_pattern") if cache_hit else None
        response.cache_hit = cache_hit is not None
        return response

    async def store_extraction_pattern(
        self,
        *,
        tenant_id: str,
        vendor_id: str,
        document_bytes: bytes,
        extraction_pattern: dict[str, Any],
    ) -> None:
        await self.semantic_cache.store(
            tenant_id=tenant_id,
            vendor_id=vendor_id,
            document_bytes=document_bytes,
            extraction_pattern=extraction_pattern,
        )


@lru_cache
def get_llm_gateway() -> LLMGateway:
    return LLMGateway()
