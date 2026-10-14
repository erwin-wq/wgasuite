import { ListFilter, SearchCheck } from "lucide-react";
import { useEffect, useState } from "react";

import type { ConnectorConfig } from "../../types";
import { UserDirectory } from "./UserDirectory";
import { UserLookup } from "./UserLookup";

interface UserDirectoryAdministrationProps {
  organizationId: string;
  organizationName: string | null;
  connectorConfig: ConnectorConfig | null;
  canSearch: boolean;
  canManageDelegates: boolean;
  onOpenGroup: (groupEmail: string) => void;
}

interface SelectedUser {
  organizationId: string;
  primaryEmail: string;
}

export function UserDirectoryAdministration({
  organizationId,
  organizationName,
  connectorConfig,
  canSearch,
  canManageDelegates,
  onOpenGroup
}: UserDirectoryAdministrationProps) {
  const [activeView, setActiveView] = useState<"directory" | "lookup">("directory");
  const [selectedUser, setSelectedUser] = useState<SelectedUser | null>(null);

  useEffect(() => {
    setActiveView("directory");
    setSelectedUser(null);
  }, [organizationId]);

  const selectedEmail =
    selectedUser?.organizationId === organizationId ? selectedUser.primaryEmail : null;

  return (
    <div className="user-directory-administration">
      <nav className="user-directory-navigation" aria-label="User administration tools">
        <button
          type="button"
          className={activeView === "directory" ? "active" : ""}
          aria-current={activeView === "directory" ? "page" : undefined}
          onClick={() => setActiveView("directory")}
        >
          <ListFilter aria-hidden="true" /> User Directory
        </button>
        <button
          type="button"
          className={activeView === "lookup" ? "active" : ""}
          aria-current={activeView === "lookup" ? "page" : undefined}
          onClick={() => {
            setSelectedUser(null);
            setActiveView("lookup");
          }}
        >
          <SearchCheck aria-hidden="true" /> Exact User Lookup
        </button>
      </nav>

      {activeView === "directory" ? (
        <UserDirectory
          organizationId={organizationId}
          organizationName={organizationName}
          connectorConfig={connectorConfig}
          canSearch={canSearch}
          onSelectUser={(primaryEmail) => {
            setSelectedUser({ organizationId, primaryEmail });
            setActiveView("lookup");
          }}
        />
      ) : (
        <UserLookup
          key={`${organizationId}:${selectedEmail ?? "manual"}`}
          organizationId={organizationId}
          organizationName={organizationName}
          connectorConfig={connectorConfig}
          canSearch={canSearch}
          canManageDelegates={canManageDelegates}
          initialEmail={selectedEmail}
          onOpenGroup={onOpenGroup}
        />
      )}
    </div>
  );
}
