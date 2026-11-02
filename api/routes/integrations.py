import uuid

from fastapi import APIRouter, HTTPException, Query, status

from api.deps import ControllerUser
from core.config import get_settings
from schemas.integrations import WebhookDeliveryResponse, WebhookSummaryResponse
from services import webhook_deliveries

router = APIRouter(tags=["integrations"])


@router.get("/webhook/summary", response_model=WebhookSummaryResponse)
async def get_webhook_summary(current_user: ControllerUser) -> WebhookSummaryResponse:
    url = get_settings().approval_webhook_url
    summary = await webhook_deliveries.delivery_summary(tenant_id=current_user.tenant_id)
    return WebhookSummaryResponse(configured=bool(url), target_url=url or None, **summary)


@router.get("/webhook/deliveries", response_model=list[WebhookDeliveryResponse])
async def list_webhook_deliveries(
    current_user: ControllerUser,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[WebhookDeliveryResponse]:
    deliveries = await webhook_deliveries.list_deliveries(
        tenant_id=current_user.tenant_id, limit=limit
    )
    return [WebhookDeliveryResponse.from_model(delivery) for delivery in deliveries]


@router.post(
    "/webhook/deliveries/{delivery_id}/retry",
    response_model=WebhookDeliveryResponse,
)
async def retry_webhook_delivery(
    delivery_id: uuid.UUID,
    current_user: ControllerUser,
) -> WebhookDeliveryResponse:
    try:
        delivery = await webhook_deliveries.retry_delivery_now(
            tenant_id=current_user.tenant_id, delivery_id=delivery_id
        )
    except webhook_deliveries.DeliveryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found") from exc
    except webhook_deliveries.DeliveryAlreadySentError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Delivery was already sent"
        ) from exc
    return WebhookDeliveryResponse.from_model(delivery)
