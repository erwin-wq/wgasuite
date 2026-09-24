from __future__ import annotations

import json
from enum import StrEnum

from googleapiclient.errors import HttpError


class GoogleWorkspaceErrorCode(StrEnum):
    CONNECTOR_NOT_CONFIGURED = "connector_not_configured"
    CREDENTIALS_NOT_FOUND = "credentials_not_found"
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_ADMIN_SUBJECT = "invalid_admin_subject"
    DELEGATION_FAILED = "delegation_failed"
    MISSING_SCOPE_OR_PERMISSION = "missing_scope_or_permission"
    GOOGLE_FORBIDDEN = "google_forbidden"
    GOOGLE_UNAUTHORIZED = "google_unauthorized"
    GOOGLE_RATE_LIMITED = "google_rate_limited"
    GOOGLE_SERVICE_UNAVAILABLE = "google_service_unavailable"
    GOOGLE_API_ERROR = "google_api_error"
    ORGANIZATION_ACCESS_DENIED = "organization_access_denied"
    ORGANIZATION_NOT_FOUND = "organization_not_found"


SAFE_ERROR_MESSAGES = {
    GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED: (
        "Google Workspace connector metadata is incomplete or not configured."
    ),
    GoogleWorkspaceErrorCode.CREDENTIALS_NOT_FOUND: (
        "Google Workspace service-account credentials were not found."
    ),
    GoogleWorkspaceErrorCode.INVALID_CREDENTIALS: (
        "Google Workspace service-account credentials are invalid."
    ),
    GoogleWorkspaceErrorCode.INVALID_ADMIN_SUBJECT: (
        "The delegated Google Workspace administrator subject is invalid."
    ),
    GoogleWorkspaceErrorCode.DELEGATION_FAILED: (
        "Google Workspace domain-wide delegation could not be applied."
    ),
    GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION: (
        "The requested Google operation needs an additional scope or permission."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN: "Google rejected the operation as forbidden.",
    GoogleWorkspaceErrorCode.GOOGLE_UNAUTHORIZED: "Google rejected the delegated credentials.",
    GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED: "Google rate-limited the operation.",
    GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE: (
        "The requested Google service is temporarily unavailable."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_API_ERROR: "The Google API operation failed.",
    GoogleWorkspaceErrorCode.ORGANIZATION_ACCESS_DENIED: (
        "The current actor cannot operate this organization's connector."
    ),
    GoogleWorkspaceErrorCode.ORGANIZATION_NOT_FOUND: "Organization not found.",
}


class GoogleWorkspaceError(Exception):
    """A typed, secret-safe connector failure suitable for service boundaries."""

    def __init__(
        self,
        code: GoogleWorkspaceErrorCode,
        *,
        retryable: bool = False,
    ) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(SAFE_ERROR_MESSAGES[code])


def map_google_api_error(error: Exception) -> GoogleWorkspaceError:
    """Map supported Google client failures without exposing upstream response content."""

    if not isinstance(error, HttpError):
        return GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_API_ERROR)

    status_code = error.resp.status
    reasons: set[str] = set()
    try:
        response_content = json.loads(error.content.decode("utf-8"))
        response_errors = response_content.get("error", {}).get("errors", [])
        reasons = {
            item.get("reason")
            for item in response_errors
            if isinstance(item, dict) and isinstance(item.get("reason"), str)
        }
    except (AttributeError, json.JSONDecodeError, UnicodeError):
        pass

    if status_code == 401:
        code = GoogleWorkspaceErrorCode.GOOGLE_UNAUTHORIZED
    elif status_code == 403 and reasons & {"accessNotConfigured", "insufficientPermissions"}:
        code = GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION
    elif status_code == 403:
        code = GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN
    elif status_code == 429:
        code = GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED
    elif status_code in {500, 502, 503, 504}:
        code = GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE
    else:
        code = GoogleWorkspaceErrorCode.GOOGLE_API_ERROR

    return GoogleWorkspaceError(
        code,
        retryable=status_code == 429 or status_code in {500, 502, 503, 504},
    )
