from __future__ import annotations

import json
import ssl
from enum import StrEnum

import httplib2
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError


class GoogleWorkspaceErrorCode(StrEnum):
    CONNECTOR_NOT_CONFIGURED = "connector_not_configured"
    CREDENTIAL_REFERENCE_MISSING = "credential_reference_missing"
    CREDENTIALS_NOT_FOUND = "credentials_not_found"
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_ADMIN_SUBJECT = "invalid_admin_subject"
    DELEGATION_FAILED = "delegation_failed"
    DELEGATION_REJECTED = "delegation_rejected"
    GOOGLE_AUTHENTICATION_REJECTED = "google_authentication_rejected"
    MISSING_SCOPE_OR_PERMISSION = "missing_scope_or_permission"
    GOOGLE_API_UNAVAILABLE = "google_api_unavailable"
    GOOGLE_FORBIDDEN = "google_forbidden"
    GOOGLE_UNAUTHORIZED = "google_unauthorized"
    GOOGLE_RATE_LIMITED = "google_rate_limited"
    GOOGLE_SERVICE_UNAVAILABLE = "google_service_unavailable"
    GOOGLE_TIMEOUT = "google_timeout"
    GOOGLE_NETWORK_ERROR = "google_network_error"
    GOOGLE_API_ERROR = "google_api_error"
    GOOGLE_USER_NOT_FOUND = "google_user_not_found"
    GOOGLE_USER_LOOKUP_MISMATCH = "google_user_lookup_mismatch"
    GOOGLE_SUBJECT_NOT_FOUND = "google_subject_not_found"
    GOOGLE_SUBJECT_MISMATCH = "google_subject_mismatch"
    ORGANIZATION_ACCESS_DENIED = "organization_access_denied"
    ORGANIZATION_NOT_FOUND = "organization_not_found"


SAFE_ERROR_MESSAGES = {
    GoogleWorkspaceErrorCode.CONNECTOR_NOT_CONFIGURED: (
        "Google Workspace connector metadata is incomplete or not configured."
    ),
    GoogleWorkspaceErrorCode.CREDENTIAL_REFERENCE_MISSING: (
        "A Google Workspace credential reference has not been configured."
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
    GoogleWorkspaceErrorCode.DELEGATION_REJECTED: (
        "Google rejected the delegated service-account credentials. Verify domain-wide "
        "delegation, the client ID, scope authorization, and delegated administrator."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_AUTHENTICATION_REJECTED: (
        "Google authentication rejected the service-account credentials."
    ),
    GoogleWorkspaceErrorCode.MISSING_SCOPE_OR_PERMISSION: (
        "Google reported that the delegated account lacks the required scope or permission."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_API_UNAVAILABLE: (
        "The Google Admin SDK Directory API is not enabled or accessible for this project."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_FORBIDDEN: (
        "Google returned 403 Forbidden. Verify domain-wide delegation, the authorized read-only "
        "scope, API access, and the delegated administrator's privileges."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_UNAUTHORIZED: (
        "Google returned 401 Unauthorized for the delegated credentials."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_RATE_LIMITED: (
        "Google rate-limited the Directory request. Try again later."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_SERVICE_UNAVAILABLE: (
        "The Google service is temporarily unavailable. Try again later."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT: (
        "The Google Directory request timed out. Check network access and try again."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR: (
        "The Google Directory request could not reach Google. Check network and DNS access."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_API_ERROR: "The Google API operation failed.",
    GoogleWorkspaceErrorCode.GOOGLE_USER_NOT_FOUND: (
        "No Google Workspace user was found for that exact address. Group addresses are not "
        "included in user lookup."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_USER_LOOKUP_MISMATCH: (
        "Google returned a user that did not match the requested primary email or alias."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_SUBJECT_NOT_FOUND: (
        "Google could not find the configured delegated administrator account."
    ),
    GoogleWorkspaceErrorCode.GOOGLE_SUBJECT_MISMATCH: (
        "Google returned a different primary account for the delegated administrator subject."
    ),
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

    if _contains_timeout(error):
        return GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_TIMEOUT, retryable=True)
    if isinstance(error, RefreshError):
        error_name = _refresh_error_name(error)
        code = (
            GoogleWorkspaceErrorCode.DELEGATION_REJECTED
            if error_name in {"invalid_grant", "unauthorized_client"}
            else GoogleWorkspaceErrorCode.GOOGLE_AUTHENTICATION_REJECTED
        )
        return GoogleWorkspaceError(code)
    if isinstance(
        error,
        (
            ConnectionError,
            httplib2.HttpLib2Error,
            OSError,
            ssl.SSLError,
            TransportError,
        ),
    ):
        return GoogleWorkspaceError(GoogleWorkspaceErrorCode.GOOGLE_NETWORK_ERROR, retryable=True)
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
    elif status_code == 404:
        code = GoogleWorkspaceErrorCode.GOOGLE_SUBJECT_NOT_FOUND
    elif status_code == 403 and "accessNotConfigured" in reasons:
        code = GoogleWorkspaceErrorCode.GOOGLE_API_UNAVAILABLE
    elif status_code == 403 and "insufficientPermissions" in reasons:
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


def _refresh_error_name(error: RefreshError) -> str | None:
    """Extract only the documented OAuth error identifier, never its description."""

    for argument in error.args:
        if isinstance(argument, dict) and isinstance(argument.get("error"), str):
            return argument["error"]
    return None


def _contains_timeout(error: Exception) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, TimeoutError):
            return True
        seen.add(id(current))
        nested_exception = next(
            (argument for argument in current.args if isinstance(argument, BaseException)),
            None,
        )
        current = current.__cause__ or current.__context__ or nested_exception
    return False
