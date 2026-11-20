import { ApiError } from "../../api/client";
import type { GoogleWorkspaceUser } from "../../types";

export function googleWorkspaceUserLookupError(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "The lookup could not be completed. Check your connection and try again.";
  }
  if (error.status === 404 || error.code === "google_user_not_found") {
    return "No Directory user was found for that address. Google Group addresses are not included.";
  }
  if (error.code === "missing_scope_or_permission" || error.code === "google_forbidden") {
    return "Google denied this lookup. Verify the delegated administrator and the authorized read-only Directory scope.";
  }
  if (error.code === "google_rate_limited") {
    return "Google rate-limited the lookup. Wait a moment and try again.";
  }
  if (
    error.code === "google_service_unavailable" ||
    error.code === "google_network_error" ||
    error.code === "google_timeout"
  ) {
    return "Google is temporarily unavailable. Try the lookup again shortly.";
  }
  if (
    error.status === 409 ||
    error.code === "connector_not_configured" ||
    error.code === "credentials_not_found"
  ) {
    return "The Google Workspace connector is not ready. Complete and test the connection first.";
  }
  if (error.status === 403) {
    return "You do not have permission to search users for this organization.";
  }
  return "The lookup could not be completed. Check the connection and try again.";
}

export function mailboxSetupLabel(value: boolean | null): string {
  if (value === true) return "Gmail mailbox set up";
  if (value === false) return "Gmail mailbox not set up";
  return "Mailbox setup unknown";
}

export function administratorLabel(user: GoogleWorkspaceUser): string {
  if (user.is_super_admin) return "Super administrator";
  if (user.is_delegated_admin) return "Delegated administrator";
  if (user.is_super_admin === null || user.is_delegated_admin === null) return "Unknown";
  return "Standard user";
}
