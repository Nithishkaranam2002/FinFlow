import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.auth import get_current_user
from api.routes import integrations
from models.user import UserRole
from services import webhook_deliveries

TENANT_ID = uuid.uuid4()
NOW = datetime(2026, 11, 2, 21, 0, tzinfo=timezone.utc)


def _delivery(**overrides):
    values = {
        "id": uuid.uuid4(),
        "tenant_id": TENANT_ID,
        "invoice_id": uuid.uuid4(),
        "event": "invoice.approved",
        "target_url": "http://n8n.test/webhook/finflow",
        "payload": {"invoice_number": "KRES-240518", "vendor": {"name": "Kestrel Ridge Electrical Supply"}},
        "status": "failed",
        "attempts": 1,
        "last_status_code": None,
        "last_error": "Could not connect to the receiver. Is it running and reachable?",
        "created_at": NOW,
        "last_attempt_at": NOW,
        "next_retry_at": None,
        "sent_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _client(role: UserRole) -> TestClient:
    app = FastAPI()
    app.include_router(integrations.router, prefix="/api/v1/integrations")
    user = SimpleNamespace(id=uuid.uuid4(), tenant_id=TENANT_ID, role=role, is_active=True)
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def webhook_url(monkeypatch) -> None:
    monkeypatch.setenv("APPROVAL_WEBHOOK_URL", "http://n8n.test/webhook/finflow")


@pytest.mark.parametrize("role", [UserRole.AP_CLERK, UserRole.APPROVER])
def test_endpoints_require_controller(role) -> None:
    client = _client(role)

    assert client.get("/api/v1/integrations/webhook/summary").status_code == 403
    assert client.get("/api/v1/integrations/webhook/deliveries").status_code == 403
    assert client.post(f"/api/v1/integrations/webhook/deliveries/{uuid.uuid4()}/retry").status_code == 403


def test_summary_reports_configuration_and_failures(monkeypatch) -> None:
    async def fake_summary(*, tenant_id):
        assert tenant_id == TENANT_ID
        return {
            "last_status": "failed",
            "last_delivery_at": NOW,
            "last_error": "Could not connect to the receiver. Is it running and reachable?",
            "next_retry_at": None,
            "last_success_at": None,
            "failures_24h": 2,
        }

    monkeypatch.setattr(webhook_deliveries, "delivery_summary", fake_summary)

    response = _client(UserRole.CONTROLLER).get("/api/v1/integrations/webhook/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["target_url"] == "http://n8n.test/webhook/finflow"
    assert body["last_status"] == "failed"
    assert body["failures_24h"] == 2


def test_list_returns_deliveries_with_invoice_and_vendor(monkeypatch) -> None:
    async def fake_list(*, tenant_id, limit):
        assert (tenant_id, limit) == (TENANT_ID, 50)
        return [_delivery()]

    monkeypatch.setattr(webhook_deliveries, "list_deliveries", fake_list)

    response = _client(UserRole.CONTROLLER).get("/api/v1/integrations/webhook/deliveries")

    assert response.status_code == 200
    [row] = response.json()
    assert row["invoice_number"] == "KRES-240518"
    assert row["vendor_name"] == "Kestrel Ridge Electrical Supply"
    assert row["status"] == "failed"
    assert row["last_error"].startswith("Could not connect")


def test_retry_now_returns_updated_delivery(monkeypatch) -> None:
    delivery_id = uuid.uuid4()

    async def fake_retry(*, tenant_id, delivery_id):
        return _delivery(id=delivery_id, status="sent", attempts=2, last_error=None, sent_at=NOW)

    monkeypatch.setattr(webhook_deliveries, "retry_delivery_now", fake_retry)

    response = _client(UserRole.CONTROLLER).post(
        f"/api/v1/integrations/webhook/deliveries/{delivery_id}/retry"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "sent"
    assert response.json()["attempts"] == 2


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (webhook_deliveries.DeliveryNotFoundError, 404),
        (webhook_deliveries.DeliveryAlreadySentError, 409),
    ],
)
def test_retry_now_error_responses(monkeypatch, error, status_code) -> None:
    async def fake_retry(*, tenant_id, delivery_id):
        raise error(str(delivery_id))

    monkeypatch.setattr(webhook_deliveries, "retry_delivery_now", fake_retry)

    response = _client(UserRole.CONTROLLER).post(
        f"/api/v1/integrations/webhook/deliveries/{uuid.uuid4()}/retry"
    )

    assert response.status_code == status_code
