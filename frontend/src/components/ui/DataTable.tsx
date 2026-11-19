import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";

import { Button } from "./Button";
import { EmptyState, ErrorState, Skeleton } from "./Feedback";
import { Select } from "./FormControls";
import { cx } from "./utils";

export type DataTableSortDirection = "ascending" | "descending" | "none";

export interface DataTableColumn<Row> {
  id: string;
  header: ReactNode;
  cell: (row: Row) => ReactNode;
  sortDirection?: DataTableSortDirection;
  onSort?: () => void;
  className?: string;
  headerClassName?: string;
}

export interface DataTableProps<Row> {
  ariaLabel: string;
  columns: readonly DataTableColumn<Row>[];
  rows: readonly Row[];
  rowKey: (row: Row) => string;
  loading?: boolean;
  error?: string | null;
  errorTitle?: string;
  onRetry?: () => void;
  errorActionLabel?: string;
  emptyTitle: string;
  emptyDescription: ReactNode;
  minWidth?: string;
  stickyLastColumn?: boolean;
  className?: string;
}

function SortIcon({ direction }: { direction: DataTableSortDirection }) {
  if (direction === "ascending") return <ArrowUp aria-hidden="true" />;
  if (direction === "descending") return <ArrowDown aria-hidden="true" />;
  return <ChevronsUpDown aria-hidden="true" />;
}

export function DataTable<Row>({
  ariaLabel,
  columns,
  rows,
  rowKey,
  loading = false,
  error = null,
  errorTitle = "Data could not be loaded",
  onRetry,
  errorActionLabel = "Try again",
  emptyTitle,
  emptyDescription,
  minWidth,
  stickyLastColumn = false,
  className
}: DataTableProps<Row>) {
  if (error) {
    return (
      <ErrorState title={errorTitle} actionLabel={onRetry ? errorActionLabel : undefined} onAction={onRetry}>
        {error}
      </ErrorState>
    );
  }

  if (loading) {
    return (
      <div className="ui-data-table__loading" role="status" aria-live="polite" aria-label={`Loading ${ariaLabel}`}>
        <span className="sr-only">Loading {ariaLabel}.</span>
        <Skeleton lines={5} />
      </div>
    );
  }

  if (rows.length === 0) {
    return <EmptyState title={emptyTitle}>{emptyDescription}</EmptyState>;
  }

  const tableStyle = minWidth ? ({ "--ui-data-table-min-width": minWidth } as CSSProperties) : undefined;

  return (
    <div className={cx("ui-data-table", stickyLastColumn && "ui-data-table--sticky-last", className)}>
      <div className="ui-data-table__viewport" tabIndex={0} role="region" aria-label={`${ariaLabel} table`}>
        <table style={tableStyle}>
          <caption className="sr-only">{ariaLabel}</caption>
          <thead>
            <tr>
              {columns.map((column) => {
                const sortable = Boolean(column.onSort);
                const direction = column.sortDirection ?? "none";
                return (
                  <th
                    key={column.id}
                    scope="col"
                    aria-sort={sortable ? direction : undefined}
                    className={column.headerClassName}
                  >
                    {sortable ? (
                      <button type="button" className="ui-data-table__sort" onClick={column.onSort}>
                        <span>{column.header}</span>
                        <SortIcon direction={direction} />
                      </button>
                    ) : column.header}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={rowKey(row)}>
                {columns.map((column) => <td key={column.id} className={column.className}>{column.cell(row)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

interface PageSizeOption {
  value: number;
  label?: string;
}

export interface DataTablePaginationProps {
  ariaLabel: string;
  page: number;
  onPrevious: () => void;
  onNext: () => void;
  previousDisabled?: boolean;
  nextDisabled?: boolean;
  pageSize?: number;
  pageSizeOptions?: readonly PageSizeOption[];
  onPageSizeChange?: (value: number) => void;
  disabled?: boolean;
}

export function DataTablePagination({
  ariaLabel,
  page,
  onPrevious,
  onNext,
  previousDisabled = false,
  nextDisabled = false,
  pageSize,
  pageSizeOptions,
  onPageSizeChange,
  disabled = false
}: DataTablePaginationProps) {
  const showPageSize = pageSize !== undefined && pageSizeOptions && onPageSizeChange;
  return (
    <nav className="ui-data-table-pagination" aria-label={ariaLabel}>
      {showPageSize ? (
        <Select
          className="ui-data-table-pagination__size"
          label="Rows per page"
          hideLabel
          aria-label="Rows per page"
          value={String(pageSize)}
          disabled={disabled}
          onChange={(event) => onPageSizeChange(Number(event.target.value))}
          options={pageSizeOptions.map((option) => ({
            value: String(option.value),
            label: option.label ?? String(option.value)
          }))}
        />
      ) : null}
      <Button variant="secondary" size="sm" disabled={disabled || previousDisabled} onClick={onPrevious}>
        Previous
      </Button>
      <span aria-current="page">Page {page + 1}</span>
      <Button variant="secondary" size="sm" disabled={disabled || nextDisabled} onClick={onNext}>
        Next
      </Button>
    </nav>
  );
}
