import { X } from "lucide-react";
import { type MouseEvent, type ReactNode, type RefObject, useEffect, useId, useRef } from "react";

import { IconButton } from "./Button";
import { cx } from "./utils";

const focusableSelector = [
  "button:not([disabled])",
  "[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  initialFocusRef?: RefObject<HTMLElement | null>;
  closeDisabled?: boolean;
  className?: string;
}

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  initialFocusRef,
  closeDisabled = false,
  className
}: ModalProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const closeDisabledRef = useRef(closeDisabled);

  useEffect(() => {
    onCloseRef.current = onClose;
    closeDisabledRef.current = closeDisabled;
  }, [closeDisabled, onClose]);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    (initialFocusRef?.current ?? dialog?.querySelector<HTMLElement>(focusableSelector) ?? dialog)?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !closeDisabledRef.current) {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector));
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocus?.focus();
    };
  }, [initialFocusRef, open]);

  if (!open) return null;

  function handleBackdrop(event: MouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !closeDisabled) onClose();
  }

  return (
    <div className="ui-modal-backdrop" onMouseDown={handleBackdrop}>
      <div
        ref={dialogRef}
        className={cx("ui-modal", className)}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
      >
        <header className="ui-modal__header">
          <div><h2 id={titleId}>{title}</h2>{description ? <p id={descriptionId}>{description}</p> : null}</div>
          <IconButton label="Close dialog" icon={<X aria-hidden="true" />} onClick={onClose} disabled={closeDisabled} />
        </header>
        <div className="ui-modal__body">{children}</div>
        {footer ? <footer className="ui-modal__footer">{footer}</footer> : null}
      </div>
    </div>
  );
}
