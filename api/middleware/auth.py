import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.rbac import ROLE_LEVEL
from core.security import verify_token
from core.tenant import set_current_tenant_id
from models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    payload = verify_token(token)

    try:
        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tenant_id"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing required claims",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_role = payload.get("role")
    if token_role and token_role != user.role.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token role mismatch",
            headers={"WWW-Authenticate": "Bearer"},
        )

    set_current_tenant_id(tenant_id)
    return user


def _require_min_role(min_role: UserRole):
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if ROLE_LEVEL[current_user.role] < ROLE_LEVEL[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {min_role.value} role or higher",
            )
        return current_user

    return Depends(role_checker)


# Cumulative RBAC: auditor > controller > approver > ap_clerk
require_ap_clerk = _require_min_role(UserRole.AP_CLERK)
require_approver = _require_min_role(UserRole.APPROVER)
require_controller = _require_min_role(UserRole.CONTROLLER)
require_auditor = _require_min_role(UserRole.AUDITOR)


def can_delete(user: User) -> bool:
    """Controllers cannot delete; only auditors may delete records."""
    return user.role == UserRole.AUDITOR


CurrentUser = Annotated[User, Depends(get_current_user)]
ApClerkUser = Annotated[User, require_ap_clerk]
ApproverUser = Annotated[User, require_approver]
ControllerUser = Annotated[User, require_controller]
AuditorUser = Annotated[User, require_auditor]
