from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.auth import (  # noqa: F401
    ApClerkUser,
    ApproverUser,
    AuditorUser,
    ControllerUser,
    CurrentUser,
    can_delete,
    get_current_user,
    require_ap_clerk,
    require_approver,
    require_auditor,
    require_controller,
)
from core.database import get_db

DbSession = Annotated[AsyncSession, Depends(get_db)]
