import {
  AlertCircle,
  CheckCircle2,
  CircleAlert,
  Info,
  SearchX,
  X
} from "lucide-react";
import { type HTMLAttributes, type ReactNode } from "react";

import { Button, IconButton } from "./Button";
import { cx } from "./utils";

export type SemanticVariant = "neutral" | "info" | "success" | "warning" | "danger";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: SemanticVariant;
  icon?: ReactNode;
}

export function Badge({ variant = "neutral", icon, className, children, ...props }: BadgeProps) {
  return <span {...props} className={cx("ui-badge", `ui-badge--${variant}`, className)}>{icon}{children}</span>;
}

const alertIcons = {
  neutral: Info,
  info: Info,
  success: CheckCircle2,
  warning: CircleAlert,
  danger: AlertCircle
};

export interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  variant?: SemanticVariant;
  title?: string;
  icon?: ReactNode;
}

export function Alert({ variant = "info", title, icon, className, children, ...props }: AlertProps) {
  const Icon = alertIcons[variant];
  return (
    <div
      {...props}
      className={cx("ui-alert", `ui-alert--${variant}`, className)}
      role={variant === "danger" ? "alert" : props.role ?? "status"}
    >
      <span className="ui-alert__icon" aria-hidden="true">{icon ?? <Icon />}</span>
      <div>{title ? <strong>{title}</strong> : null}<div>{children}</div></div>
    </div>
  );
}

export interface ToastProps {
  variant?: Exclude<SemanticVariant, "neutral">;
  title: string;
  children?: ReactNode;
  onDismiss?: () => void;
}

export function Toast({ variant = "info", title, children, onDismiss }: ToastProps) {
  return (
    <div className={cx("ui-toast", `ui-toast--${variant}`)} role={variant === "danger" ? "alert" : "status"}>
      <div><strong>{title}</strong>{children ? <p>{children}</p> : null}</div>
      {onDismiss ? <IconButton size="sm" label="Dismiss notification" icon={<X aria-hidden="true" />} onClick={onDismiss} /> : null}
    </div>
  );
}

export function ToastRegion({ children, label = "Notifications" }: { children: ReactNode; label?: string }) {
  return <div className="ui-toast-region" aria-label={label} aria-live="polite">{children}</div>;
}

export function Skeleton({ className, lines = 1 }: { className?: string; lines?: number }) {
  return (
    <div className={cx("ui-skeleton-group", className)} aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => <span className="ui-skeleton" key={index} />)}
    </div>
  );
}

interface StateProps {
  title: string;
  children?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  icon?: ReactNode;
  className?: string;
}

export function EmptyState({ title, children, actionLabel, onAction, icon, className }: StateProps) {
  return (
    <section className={cx("ui-state", className)} role="status">
      <span className="ui-state__icon" aria-hidden="true">{icon ?? <SearchX />}</span>
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
      {actionLabel && onAction ? <Button variant="secondary" onClick={onAction}>{actionLabel}</Button> : null}
    </section>
  );
}

export function ErrorState({ title, children, actionLabel, onAction, icon, className }: StateProps) {
  return (
    <section className={cx("ui-state", "ui-state--error", className)} role="alert">
      <span className="ui-state__icon" aria-hidden="true">{icon ?? <AlertCircle />}</span>
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
      {actionLabel && onAction ? <Button variant="secondary" onClick={onAction}>{actionLabel}</Button> : null}
    </section>
  );
}
