import { Search, X } from "lucide-react";
import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  useId
} from "react";

import { IconButton } from "./Button";
import { cx } from "./utils";

interface FieldMetaProps {
  label: string;
  hint?: string;
  error?: string;
  hideLabel?: boolean;
  className?: string;
}

function FieldMeta({
  id,
  label,
  hint,
  error,
  hideLabel,
  className,
  children
}: FieldMetaProps & { id: string; children: ReactNode }) {
  return (
    <div className={cx("ui-field", error && "ui-field--invalid", className)}>
      <label className={hideLabel ? "sr-only" : "ui-field__label"} htmlFor={id}>{label}</label>
      {children}
      {error ? <p id={`${id}-error`} className="ui-field__error" role="alert">{error}</p> : null}
      {!error && hint ? <p id={`${id}-hint`} className="ui-field__hint">{hint}</p> : null}
    </div>
  );
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement>, FieldMetaProps {
  leadingIcon?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, hideLabel, leadingIcon, className, id: providedId, ...props },
  ref
) {
  const generatedId = useId();
  const id = providedId ?? generatedId;
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <FieldMeta id={id} label={label} hint={hint} error={error} hideLabel={hideLabel} className={className}>
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
  { label, hint, error, hideLabel, className, id: providedId, options, ...props },
  ref
) {
  const generatedId = useId();
  const id = providedId ?? generatedId;
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <FieldMeta id={id} label={label} hint={hint} error={error} hideLabel={hideLabel} className={className}>
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
