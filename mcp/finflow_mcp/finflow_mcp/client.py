"""Small authenticated, read-only client for the FinFlow REST API."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

DEFAULT_API_URL = "http://localhost:8000"
PAGE_SIZE = 100
MAX_INVOICES = 2000


class FinFlowConfigError(ToolError):
    """Expected setup problem; ToolError makes the message visible to the model."""


class FinFlowClient:
    """Logs in once with FINFLOW_EMAIL / FINFLOW_PASSWORD and reuses the session cookie."""

    def __init__(self) -> None:
        self.base_url = os.environ.get("FINFLOW_API_URL", DEFAULT_API_URL).rstrip("/")
        self._email = os.environ.get("FINFLOW_EMAIL", "")
        self._password = os.environ.get("FINFLOW_PASSWORD", "")
        self._http: httpx.AsyncClient | None = None
        self._logged_in = False
        self._login_lock = asyncio.Lock()
        self._vendor_names: dict[str, str] | None = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=f"{self.base_url}/api/v1", timeout=15.0)
        return self._http

    async def _login(self) -> None:
        if not self._email or not self._password:
            raise FinFlowConfigError(
                "FINFLOW_EMAIL and FINFLOW_PASSWORD must be set in the MCP server's env "
                "(claude_desktop_config.json)."
            )
        async with self._login_lock:
            try:
                response = await self._client().post(
                    "/auth/login",
                    data={"username": self._email, "password": self._password},
                )
            except httpx.ConnectError as exc:
                raise FinFlowConfigError(
                    f"Cannot reach the FinFlow API at {self.base_url}. Is it running?"
                ) from exc
            if response.status_code == 401:
                raise FinFlowConfigError("FinFlow rejected FINFLOW_EMAIL / FINFLOW_PASSWORD.")
            response.raise_for_status()
            self._logged_in = True

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET a JSON resource; logs in on first use and once more if the session expired."""
        if not self._logged_in:
            await self._login()
        try:
            response = await self._client().get(path, params=params)
        except httpx.ConnectError as exc:
            raise FinFlowConfigError(
                f"Cannot reach the FinFlow API at {self.base_url}. Is it running?"
            ) from exc
        if response.status_code == 401:
            self._logged_in = False
            await self._login()
            response = await self._client().get(path, params=params)
        response.raise_for_status()
        return response.json()

    async def list_invoices(self, **filters: Any) -> list[dict[str, Any]]:
        """All invoices matching the filters, following pagination."""
        invoices: list[dict[str, Any]] = []
        page = 1
        while len(invoices) < MAX_INVOICES:
            data = await self.get(
                "/invoices/",
                {**{k: v for k, v in filters.items() if v is not None}, "page": page, "page_size": PAGE_SIZE},
            )
            invoices.extend(data["items"])
            if len(invoices) >= data["total"] or not data["items"]:
                break
            page += 1
        return invoices

    async def vendor_names(self) -> dict[str, str]:
        if self._vendor_names is None:
            vendors = await self.get("/vendors/")
            self._vendor_names = {vendor["id"]: vendor["name"] for vendor in vendors}
        return self._vendor_names
