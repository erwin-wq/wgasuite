import { Search, X } from "lucide-react";
import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useId
} from "react";

import { IconButton } from "./Button";
import { cx } from "./utils";

interface FieldMetaProps {
  label: string;
  hint?: string;
  error?: string;
  hideLabel?: boolean;
  required?: boolean;
  optional?: boolean;
  className?: string;
}

function FieldMeta({
  id,
  label,
  hint,
  error,
  hideLabel,
  required,
  optional,
  className,
  children
}: FieldMetaProps & { id: string; children: ReactNode }) {
  return (
    <div className={cx("ui-field", error && "ui-field--invalid", className)}>
      <label className={hideLabel ? "sr-only" : cx("ui-field__label", required && "ui-field__label--required")} htmlFor={id}>
        {label}
        {!required && optional ? <span className="ui-field__optional"> (optional)</span> : null}
      </label>
      {children}
      {error ? <p id={`${id}-error`} className="ui-field__error" role="alert">{error}</p> : null}
      {hint ? <p id={`${id}-hint`} className="ui-field__hint">{hint}</p> : null}
    </div>
  );
}

function describedByIds(id: string, hint?: string, error?: string): string | undefined {
  const ids = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean);
  return ids.length > 0 ? ids.join(" ") : undefined;
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement>, FieldMetaProps {
  leadingIcon?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, hideLabel, optional, leadingIcon, className, id: providedId, ...props },
  ref
) {
  const generatedId = useId();
  const id = providedId ?? generatedId;
  const describedBy = describedByIds(id, hint, error);
  return (
    <FieldMeta id={id} label={label} hint={hint} error={error} hideLabel={hideLabel} required={props.required} optional={optional} className={className}>
      <span className={cx("ui-field__control", Boolean(leadingIcon) && "ui-field__control--with-icon")}>
        {leadingIcon ? <span className="ui-field__leading" aria-hidden="true">{leadingIcon}</span> : null}
        <input
          {...props}
          ref={ref}
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
        />
      </span>
    </FieldMeta>
  );
});

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement>, FieldMetaProps {
  options: readonly SelectOption[];
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, hideLabel, optional, className, id: providedId, options, ...props },
  ref
) {
  const generatedId = useId();
  const id = providedId ?? generatedId;
  const describedBy = describedByIds(id, hint, error);
  return (
    <FieldMeta id={id} label={label} hint={hint} error={error} hideLabel={hideLabel} required={props.required} optional={optional} className={className}>
      <select
        {...props}
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>
        ))}
      </select>
    </FieldMeta>
  );
});

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement>, FieldMetaProps {}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, hideLabel, optional, className, id: providedId, ...props },
  ref
) {
  const generatedId = useId();
  const id = providedId ?? generatedId;
  const describedBy = describedByIds(id, hint, error);
  return (
    <FieldMeta
      id={id}
      label={label}
      hint={hint}
      error={error}
      hideLabel={hideLabel}
      required={props.required}
      optional={optional}
      className={className}
    >
      <textarea
        {...props}
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
      />
    </FieldMeta>
  );
});

export interface SearchFieldProps extends Omit<InputProps, "type" | "leadingIcon"> {
  onClear?: () => void;
}

export const SearchField = forwardRef<HTMLInputElement, SearchFieldProps>(function SearchField(
  { onClear, value, defaultValue, className, ...props },
  ref
) {
  const hasValue = String(value ?? defaultValue ?? "").length > 0;
  return (
    <div className={cx("ui-search-field", className)}>
      <Input {...props} ref={ref} type="search" value={value} defaultValue={defaultValue} leadingIcon={<Search />} />
      {onClear && hasValue ? (
        <IconButton
          className="ui-search-field__clear"
          size="sm"
          label="Clear search"
          icon={<X aria-hidden="true" />}
          onClick={onClear}
        />
      ) : null}
    </div>
  );
});
