PLATFORM_ADMIN = "platform_admin"
PLATFORM_SUPPORT = "platform_support"
PLATFORM_CUSTOMER_USER = "customer_user"

CUSTOMER_ADMIN = "customer_admin"
CUSTOMER_USER = "customer_user"
CUSTOMER_VIEWER = "customer_viewer"

PLATFORM_ROLES = {
    PLATFORM_ADMIN,
    PLATFORM_SUPPORT,
    PLATFORM_CUSTOMER_USER,
}

CUSTOMER_ROLES = {
    CUSTOMER_ADMIN,
    CUSTOMER_USER,
    CUSTOMER_VIEWER,
}


def is_platform_admin_role(role: str) -> bool:
    return role == PLATFORM_ADMIN


def is_valid_customer_role(role: str) -> bool:
    return role in CUSTOMER_ROLES
