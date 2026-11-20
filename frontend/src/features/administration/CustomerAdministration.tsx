import { Building2, Plus } from "lucide-react";
import { type FormEvent, useMemo, useRef, useState } from "react";

import { Button } from "../../components/ui/Button";
import { DataTable, type DataTableColumn } from "../../components/ui/DataTable";
import { Badge } from "../../components/ui/Feedback";
import { Input, Select, Textarea } from "../../components/ui/FormControls";
import { Modal } from "../../components/ui/Modal";
import type { Customer, Organization } from "../../types";

interface CustomerAdministrationProps {
  customers: Customer[];
  organizations: Organization[];
  selectedCustomerId: string;
  isLoading: boolean;
  isSaving: boolean;
  name: string;
  slug: string;
  contactName: string;
  contactEmail: string;
  status: string;
  notes: string;
  onNameChange: (value: string) => void;
  onSlugChange: (value: string) => void;
  onContactNameChange: (value: string) => void;
  onContactEmailChange: (value: string) => void;
  onStatusChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onCreate: (event: FormEvent<HTMLFormElement>) => Promise<boolean>;
  onSelectCustomer: (customerId: string) => void;
}

function statusVariant(status: string): "success" | "warning" | "neutral" {
  if (status === "active") return "success";
  if (status === "prospect") return "warning";
  return "neutral";
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value));
}

export function CustomerAdministration({
  customers,
  organizations,
  selectedCustomerId,
  isLoading,
  isSaving,
  name,
  slug,
  contactName,
  contactEmail,
  status,
  notes,
  onNameChange,
  onSlugChange,
  onContactNameChange,
  onContactEmailChange,
  onStatusChange,
  onNotesChange,
  onCreate,
  onSelectCustomer
}: CustomerAdministrationProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const createTriggerRef = useRef<HTMLButtonElement>(null);
  const organizationCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const organization of organizations) {
      if (organization.customer_id) {
        counts.set(organization.customer_id, (counts.get(organization.customer_id) ?? 0) + 1);
      }
    }
    return counts;
  }, [organizations]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    if (await onCreate(event)) setCreateOpen(false);
  }

  const columns: DataTableColumn<Customer>[] = [
    {
      id: "customer",
      header: "Customer",
      cell: (customer) => (
        <span className="admin-primary-cell">
          <strong>{customer.name}</strong>
          <span>{customer.slug}</span>
        </span>
      )
    },
    {
      id: "status",
      header: "Status",
      cell: (customer) => <Badge variant={statusVariant(customer.status)}>{customer.status}</Badge>
    },
    {
      id: "contact",
      header: "Contact",
      cell: (customer) => (
        <span className="admin-primary-cell">
          <strong>{customer.contact_name ?? "Not provided"}</strong>
          <span>{customer.contact_email ?? "No contact email"}</span>
        </span>
      )
    },
    {
      id: "organizations",
      header: "Organizations",
      cell: (customer) => organizationCounts.get(customer.id) ?? 0
    },
    {
      id: "updated",
      header: "Updated",
      cell: (customer) => formatDate(customer.updated_at)
    },
    {
      id: "context",
      header: <span className="sr-only">Workspace context</span>,
      cell: (customer) => customer.id === selectedCustomerId ? (
        <Badge variant="info">Active context</Badge>
      ) : (
        <Button variant="secondary" size="sm" onClick={() => onSelectCustomer(customer.id)}>
          Use context
        </Button>
      )
    }
  ];

  return (
    <section className="administration-page" aria-label="Customer administration">
      <div className="administration-toolbar">
        <div>
          <h2>Customer directory</h2>
          <p>The global workspace selector remains the authoritative active context.</p>
        </div>
        <Button ref={createTriggerRef} onClick={() => setCreateOpen(true)}>
          <Plus aria-hidden="true" /> Create customer
        </Button>
      </div>

      <DataTable
        ariaLabel="Platform customers"
        columns={columns}
        rows={customers}
        rowKey={(customer) => customer.id}
        loading={isLoading}
        emptyTitle="No customers"
        emptyDescription="Create the first customer context for this platform."
        minWidth="58rem"
        stickyLastColumn
        className="administration-data-table"
      />

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create customer"
        description="Add a platform customer context. Required fields are marked."
        restoreFocusRef={createTriggerRef}
        closeDisabled={isSaving}
        className="administration-form-modal"
        footer={(
          <>
            <Button variant="secondary" onClick={() => setCreateOpen(false)} disabled={isSaving}>Cancel</Button>
            <Button type="submit" form="create-customer-form" loading={isSaving} loadingLabel="Creating customer" disabled={!name.trim() || !slug.trim()}>
              Create customer
            </Button>
          </>
        )}
      >
        <form id="create-customer-form" className="administration-form" onSubmit={(event) => void submit(event)}>
          <Input label="Customer name" value={name} onChange={(event) => onNameChange(event.target.value)} placeholder="Northstar Labs" required autoFocus />
          <Input label="Slug" value={slug} onChange={(event) => onSlugChange(event.target.value)} placeholder="northstar-labs" required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" hint="Lowercase letters, numbers, and hyphens." />
          <div className="administration-form-grid">
            <Input label="Contact name" optional value={contactName} onChange={(event) => onContactNameChange(event.target.value)} placeholder="Alex Morgan" />
            <Input label="Contact email" optional type="email" value={contactEmail} onChange={(event) => onContactEmailChange(event.target.value)} placeholder="alex@example.invalid" />
          </div>
          <Select label="Status" value={status} onChange={(event) => onStatusChange(event.target.value)} options={[
            { value: "active", label: "Active" },
            { value: "prospect", label: "Prospect" },
            { value: "inactive", label: "Inactive" }
          ]} />
          <Textarea label="Notes" optional rows={4} value={notes} onChange={(event) => onNotesChange(event.target.value)} placeholder="Internal context only" />
          <div className="administration-form-note"><Building2 aria-hidden="true" />Customer creation is restricted to platform administrators.</div>
        </form>
      </Modal>
    </section>
  );
}
