import { ListFilter, SearchCheck } from "lucide-react";
import { useEffect, useState } from "react";

import { Tabs } from "../../components/ui/Tabs";
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
  view?: "directory" | "lookup";
  onViewChange?: (view: "directory" | "lookup") => void;
  hideNavigation?: boolean;
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
  onOpenGroup,
  view,
  onViewChange,
  hideNavigation = false
}: UserDirectoryAdministrationProps) {
  const [internalView, setInternalView] = useState<"directory" | "lookup">("directory");
  const [selectedUser, setSelectedUser] = useState<SelectedUser | null>(null);
  const activeView = view ?? internalView;

  function setActiveView(nextView: "directory" | "lookup") {
    setInternalView(nextView);
    onViewChange?.(nextView);
  }

  useEffect(() => {
    setInternalView("directory");
    setSelectedUser(null);
  }, [organizationId]);

  const selectedEmail =
    selectedUser?.organizationId === organizationId ? selectedUser.primaryEmail : null;

  return (
    <div className="user-directory-administration">
      {!hideNavigation && (
        <Tabs
          className="user-directory-navigation"
          ariaLabel="User administration tools"
          activeId={activeView}
          items={[
            { id: "directory", label: "User Directory", icon: <ListFilter aria-hidden="true" /> },
            { id: "lookup", label: "Exact User Lookup", icon: <SearchCheck aria-hidden="true" /> }
          ]}
          onChange={(nextView) => {
            if (nextView === "lookup") setSelectedUser(null);
            setActiveView(nextView === "lookup" ? "lookup" : "directory");
          }}
        />
      )}

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
