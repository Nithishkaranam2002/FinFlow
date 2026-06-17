"""LangGraph checkpoint persistence (PostgreSQL in production, memory in dev)."""

from __future__ import annotations

from typing import Any

import structlog

from core.config import get_settings

logger = structlog.get_logger(__name__)

_checkpointer: Any | None = None
_checkpointer_conn: Any | None = None
_initialized = False


async def init_checkpointer() -> None:
    """Initialize and migrate the LangGraph checkpoint store."""
    global _checkpointer, _checkpointer_conn, _initialized
    if _initialized:
        return

    settings = get_settings()
    if settings.use_postgres_checkpointer:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg import AsyncConnection
        from psycopg.rows import dict_row

        _checkpointer_conn = await AsyncConnection.connect(
            settings.database_sync_url,
            autocommit=True,
            prepare_threshold=0,
            row_factory=dict_row,
        )
        saver = AsyncPostgresSaver(conn=_checkpointer_conn)
        await saver.setup()
        _checkpointer = saver
        logger.info("langgraph_checkpointer_initialized", backend="postgres")
    else:
        from langgraph.checkpoint.memory import MemorySaver

        _checkpointer = MemorySaver()
        logger.info("langgraph_checkpointer_initialized", backend="memory")

    _initialized = True


def get_checkpointer() -> Any:
    """Return the active checkpointer (memory fallback before app startup)."""
    if _checkpointer is not None:
        return _checkpointer
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


async def close_checkpointer() -> None:
    """Release checkpointer resources on shutdown."""
    global _checkpointer, _checkpointer_conn, _initialized
    if _checkpointer_conn is not None:
        await _checkpointer_conn.close()
    _checkpointer = None
    _checkpointer_conn = None
    _initialized = False
