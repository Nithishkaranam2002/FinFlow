"""Langfuse observability helpers for FinFlow agents."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, TypeVar

import structlog
from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler

from core.config import Settings, get_settings

logger = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_STATE_EXCLUDED_KEYS = {"raw_file_bytes", "file_base64"}


@functools.lru_cache
def get_langfuse_client() -> Langfuse:
    settings = get_settings()
    return Langfuse(
        public_key=settings.langfuse_public_key or None,
        secret_key=settings.langfuse_secret_key or None,
        host=str(settings.langfuse_host),
    )


def _build_trace_tags(
    *,
    tenant_id: str,
    invoice_id: str,
    agent_name: str,
    environment: str,
) -> list[str]:
    return [
        f"tenant_id:{tenant_id}",
        f"invoice_id:{invoice_id}",
        f"agent_name:{agent_name}",
        f"environment:{environment}",
    ]


def get_langfuse_callback_handler(
    tenant_id: str,
    invoice_id: str,
    agent_name: str,
) -> CallbackHandler:
    """Return a LangChain callback handler scoped to this trace context."""
    settings = get_settings()
    return CallbackHandler(public_key=settings.langfuse_public_key or None)


def sanitize_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in state.items():
        if key in _STATE_EXCLUDED_KEYS:
            if isinstance(value, (bytes, bytearray)):
                sanitized[key] = f"<bytes:{len(value)}>"
            elif isinstance(value, str) and len(value) > 256:
                sanitized[key] = f"<str:{len(value)}>"
            else:
                sanitized[key] = "<redacted>"
            continue
        if isinstance(value, (bytes, bytearray)):
            sanitized[key] = f"<bytes:{len(value)}>"
        else:
            sanitized[key] = value
    return sanitized


def diff_state(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    before = sanitize_state(before)
    after = sanitize_state(after)
    changed: dict[str, Any] = {}
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            changed[key] = {"before": before.get(key), "after": after.get(key)}
    return changed


def extract_trace_ids() -> dict[str, str | None]:
    client = get_langfuse_client()
    trace_id = client.get_current_trace_id()
    observation_id = client.get_current_observation_id()
    return {"trace_id": trace_id, "observation_id": observation_id}


def trace_agent_step(agent_name: str) -> Callable[[F], F]:
    """Wrap an async agent node with a Langfuse span, I/O logging, and timing."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(state: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
            settings = get_settings()
            tenant_id = str(state.get("tenant_id") or "unknown")
            invoice_id = str(
                state.get("invoice_id") or state.get("statement_id") or "unknown"
            )
            tags = _build_trace_tags(
                tenant_id=tenant_id,
                invoice_id=invoice_id,
                agent_name=agent_name,
                environment=settings.app_env,
            )
            metadata = {
                "tenant_id": tenant_id,
                "invoice_id": invoice_id,
                "agent_name": agent_name,
                "environment": settings.app_env,
                "node": func.__name__,
            }
            client = get_langfuse_client()
            input_state = sanitize_state(state)
            started = time.perf_counter()

            with propagate_attributes(
                tags=tags,
                metadata=metadata,
                trace_name=f"{agent_name}.{func.__name__}",
            ):
                with client.start_as_current_observation(
                    as_type="span",
                    name=func.__name__,
                    input={"state": input_state},
                    metadata=metadata,
                ) as span:
                    try:
                        result = await func(state, *args, **kwargs)
                        duration_ms = int((time.perf_counter() - started) * 1000)
                        merged_state = {**state, **(result or {})}
                        span.update(
                            output={
                                "state_diff": diff_state(state, merged_state),
                                "duration_ms": duration_ms,
                            },
                            metadata={
                                **metadata,
                                "duration_ms": duration_ms,
                            },
                        )
                        client.flush()
                        return result
                    except Exception as exc:
                        duration_ms = int((time.perf_counter() - started) * 1000)
                        span.update(
                            level="ERROR",
                            status_message=str(exc),
                            output={"error": str(exc), "duration_ms": duration_ms},
                            metadata={**metadata, "duration_ms": duration_ms},
                        )
                        client.flush()
                        logger.exception(
                            "agent_step_failed",
                            agent=agent_name,
                            node=func.__name__,
                            tenant_id=tenant_id,
                            invoice_id=invoice_id,
                        )
                        raise

        return wrapper  # type: ignore[return-value]

    return decorator


def score_extraction_trace(
    *,
    trace_id: str,
    value: float,
    comment: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    settings = get_settings()
    if not trace_id or not settings.langfuse_public_key:
        logger.warning("langfuse_score_skipped", trace_id=trace_id, reason="disabled_or_missing_trace")
        return

    client = get_langfuse_client()
    client.create_score(
        name="extraction_quality",
        value=value,
        trace_id=trace_id,
        comment=comment,
        data_type="NUMERIC",
        metadata=metadata,
    )
    client.flush()


def ensure_langfuse_env(settings: Settings | None = None) -> None:
    """Align process env vars with settings for get_client() callers."""
    import os

    cfg = settings or get_settings()
    if cfg.langfuse_public_key:
        os.environ.setdefault("LANGFUSE_PUBLIC_KEY", cfg.langfuse_public_key)
    if cfg.langfuse_secret_key:
        os.environ.setdefault("LANGFUSE_SECRET_KEY", cfg.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", str(cfg.langfuse_host))


ensure_langfuse_env()
