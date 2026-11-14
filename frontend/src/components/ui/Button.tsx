import { LoaderCircle } from "lucide-react";
import {
  forwardRef,
  type ButtonHTMLAttributes,
  type ReactNode
} from "react";

import { cx } from "./utils";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
export type ComponentSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ComponentSize;
  loading?: boolean;
  loadingLabel?: string;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    loadingLabel = "Working",
    disabled,
    className,
    children,
    type = "button",
    ...props
  },
  ref
) {
  return (
    <button
      {...props}
      ref={ref}
      type={type}
      className={cx("ui-button", `ui-button--${variant}`, `ui-button--${size}`, className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading ? <LoaderCircle className="ui-spin" aria-hidden="true" /> : null}
      {loading ? <span className="sr-only">{loadingLabel}</span> : null}
      {children}
    </button>
  );
});

export interface IconButtonProps extends Omit<ButtonProps, "children"> {
  label: string;
  icon: ReactNode;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, icon, className, variant = "ghost", size = "md", ...props },
  ref
) {
  return (
    <Button
      {...props}
      ref={ref}
      variant={variant}
      size={size}
      className={cx("ui-icon-button", className)}
      aria-label={label}
      title={props.title ?? label}
    >
      {icon}
    </Button>
  );
});
