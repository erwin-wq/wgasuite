import { Building2, Link2, Plus } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";

import { Button } from "../../components/ui/Button";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { Alert, Badge, EmptyState } from "../../components/ui/Feedback";
import { Input, Textarea } from "../../components/ui/FormControls";
import { Modal } from "../../components/ui/Modal";
import type { Customer, Organization } from "../../types";

interface OrganizationAdministrationProps {
  customer: Customer | null;
  organizations: Organization[];
  selectedOrganizationId: string;
  isLoading: boolean;
  canCreate: boolean;
  isSaving: boolean;
  name: string;
  description: string;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onCreate: (event: FormEvent<HTMLFormElement>) => Promise<boolean>;
  onSelectOrganization: (organizationId: string) => void;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
}

export function OrganizationAdministration({
  customer,
  organizations,
  selectedOrganizationId,
  isLoading,
  canCreate,
  isSaving,
  name,
  description,
  onNameChange,
  onDescriptionChange,
  onCreate,
  onSelectOrganization
}: OrganizationAdministrationProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const createTriggerRef = useRef<HTMLButtonElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    if (await onCreate(event)) setCreateOpen(false);
  }

  const columns: DataTableColumn<Organization>[] = [
    {
      id: "organization",
      header: "Organization",
      cell: (organization) => (
        <span className="admin-primary-cell">
          <strong>{organization.name}</strong>
          <span>{organization.description ?? "No description"}</span>
        </span>
      )
    },
    { id: "customer", header: "Customer", cell: () => customer?.name ?? "Not linked" },
    { id: "updated", header: "Updated", cell: (organization) => formatDate(organization.updated_at) },
    {
      id: "context",
      header: <span className="sr-only">Workspace context</span>,
      cell: (organization) => organization.id === selectedOrganizationId ? (
        <Badge variant="info">Active workspace</Badge>
      ) : (
        <Button variant="secondary" size="sm" onClick={() => onSelectOrganization(organization.id)}>
          Use workspace
        </Button>
      )
    }
  ];

  if (!customer) {
    return (
      <EmptyState title="Select a customer" icon={<Building2 aria-hidden="true" />}>
        Choose a customer in the global workspace selector before managing organizations.
      </EmptyState>
    );
  }

  return (
    <section className="administration-page" aria-label="Organization administration">
      <Alert variant="info" icon={<Link2 aria-hidden="true" />}>
        Showing organizations linked to <strong>{customer.name}</strong>. Change customer context in the global header.
      </Alert>
      <div className="administration-toolbar">
        <div>
          <h2>Organizations</h2>
          <p>Organization identity and customer relationships are preserved exactly as stored.</p>
        </div>
        {canCreate ? (
          <Button ref={createTriggerRef} onClick={() => setCreateOpen(true)}>
            <Plus aria-hidden="true" /> Create organization
          </Button>
        ) : null}
      </div>

      <DataTable
        ariaLabel={`Organizations for ${customer.name}`}
        columns={columns}
        rows={organizations}
        rowKey={(organization) => organization.id}
        loading={isLoading}
        emptyTitle="No organizations"
        emptyDescription="This customer does not have any linked organizations yet."
        minWidth="48rem"
        stickyLastColumn
        className="administration-data-table"
      />

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create organization"
        description={`The new organization will be linked to ${customer.name}.`}
        restoreFocusRef={createTriggerRef}
        closeDisabled={isSaving}
        className="administration-form-modal"
        footer={(
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)} disabled={isSaving}>Cancel</Button>
            <Button type="submit" form="create-organization-form" loading={isSaving} loadingLabel="Creating organization" disabled={!name.trim()}>
              Create organization
            </Button>
          </>
        )}
      >
        <form id="create-organization-form" className="administration-form" onSubmit={(event) => void submit(event)}>
          <Input label="Organization name" value={name} onChange={(event) => onNameChange(event.target.value)} placeholder="Northstar Workspace" required autoFocus />
          <Textarea label="Description" optional rows={4} value={description} onChange={(event) => onDescriptionChange(event.target.value)} placeholder="Internal organization context" />
        </form>
      </Modal>
    </section>
  );
}
