"""Role-based access control levels shared across API and services."""

from models.user import User, UserRole

ROLE_LEVEL: dict[UserRole, int] = {
    UserRole.AP_CLERK: 1,
    UserRole.APPROVER: 2,
    UserRole.CONTROLLER: 3,
    UserRole.AUDITOR: 4,
}


def user_meets_required_role(user: User, required_role: str) -> bool:
    try:
        required = UserRole(required_role)
    except ValueError:
        return False
    return ROLE_LEVEL[user.role] >= ROLE_LEVEL[required]
