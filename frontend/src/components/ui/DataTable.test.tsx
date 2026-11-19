import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DataTable, DataTablePagination, type DataTableColumn } from "./DataTable";

interface ExampleRow {
  id: string;
  name: string;
  optional?: string;
}

const rows: ExampleRow[] = [
  { id: "1", name: "A very long enterprise directory record name", optional: "Available" },
  { id: "2", name: "Second record" }
];

describe("DataTable", () => {
  it("renders typed columns, optional values, a caption, and keyboard-operable actions", async () => {
    const open = vi.fn();
    const columns: DataTableColumn<ExampleRow>[] = [
      { id: "name", header: "Name", cell: (row) => row.name },
      { id: "optional", header: "Optional", cell: (row) => row.optional ?? "Not available" },
      { id: "actions", header: <span className="sr-only">Actions</span>, cell: (row) => <button onClick={() => open(row.id)}>Open</button> }
    ];
    const interaction = userEvent.setup();
    render(
      <DataTable
        ariaLabel="Example records"
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        emptyTitle="No records"
        emptyDescription="Nothing matched."
      />
    );

    const table = screen.getByRole("table", { name: "Example records" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(screen.getByText("Not available")).toBeVisible();
    await interaction.click(screen.getAllByRole("button", { name: "Open" })[1]);
    expect(open).toHaveBeenCalledWith("2");
  });

  it("exposes accessible sort state and delegates sorting without mutating rows", async () => {
    const onSort = vi.fn();
    const interaction = userEvent.setup();
    render(
      <DataTable
        ariaLabel="Sortable records"
        columns={[{ id: "name", header: "Name", cell: (row: ExampleRow) => row.name, sortDirection: "descending", onSort }]}
        rows={rows}
        rowKey={(row) => row.id}
        emptyTitle="No records"
        emptyDescription="Nothing matched."
      />
    );

    expect(screen.getByRole("columnheader", { name: "Name" })).toHaveAttribute("aria-sort", "descending");
    await interaction.click(screen.getByRole("button", { name: "Name" }));
    expect(onSort).toHaveBeenCalledTimes(1);
    expect(screen.getAllByRole("row")[1]).toHaveTextContent(rows[0].name);
  });

  it("renders loading, empty, and recoverable error states", async () => {
    const retry = vi.fn();
    const interaction = userEvent.setup();
    const baseProps = {
      ariaLabel: "Stateful records",
      columns: [{ id: "name", header: "Name", cell: (row: ExampleRow) => row.name }],
      rows: [] as ExampleRow[],
      rowKey: (row: ExampleRow) => row.id,
      emptyTitle: "No records",
      emptyDescription: "Nothing matched."
    };
    const view = render(<DataTable {...baseProps} loading />);
    expect(screen.getByRole("status", { name: "Loading Stateful records" })).toBeVisible();

    view.rerender(<DataTable {...baseProps} />);
    expect(screen.getByRole("heading", { name: "No records" })).toBeVisible();

    view.rerender(<DataTable {...baseProps} error="Safe error message" onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Safe error message");
    await interaction.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("enforces pagination boundaries and reports page-size changes", async () => {
    const previous = vi.fn();
    const next = vi.fn();
    const changeSize = vi.fn();
    const interaction = userEvent.setup();
    render(
      <DataTablePagination
        ariaLabel="Record pages"
        page={0}
        onPrevious={previous}
        onNext={next}
        previousDisabled
        pageSize={25}
        pageSizeOptions={[{ value: 25 }, { value: 50 }]}
        onPageSizeChange={changeSize}
      />
    );

    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await interaction.click(screen.getByRole("button", { name: "Next" }));
    expect(next).toHaveBeenCalledTimes(1);
    await interaction.selectOptions(screen.getByLabelText("Rows per page"), "50");
    expect(changeSize).toHaveBeenCalledWith(50);
  });
});
