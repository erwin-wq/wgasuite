import { ChevronDown } from "lucide-react";
import {
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState
} from "react";

import { Button, type ButtonVariant } from "./Button";
import { cx } from "./utils";

export interface DropdownItem {
  id: string;
  label: string;
  icon?: ReactNode;
  disabled?: boolean;
  destructive?: boolean;
  onSelect: () => void;
}

export interface DropdownProps {
  label: string;
  trigger: ReactNode;
  items: readonly DropdownItem[];
  variant?: ButtonVariant;
  align?: "start" | "end";
  disabled?: boolean;
  className?: string;
}

export function Dropdown({
  label,
  trigger,
  items,
  variant = "secondary",
  align = "start",
  disabled,
  className
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!open) return;
    itemRefs.current.find((item) => item && !item.disabled)?.focus();
    function handleOutside(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [open]);

  function closeAndRestoreFocus() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  function handleMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeAndRestoreFocus();
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    const enabled = itemRefs.current.filter((item): item is HTMLButtonElement => Boolean(item && !item.disabled));
    const current = enabled.indexOf(document.activeElement as HTMLButtonElement);
    const direction = event.key === "ArrowDown" ? 1 : -1;
    const next = (current + direction + enabled.length) % enabled.length;
    enabled[next]?.focus();
  }

  return (
    <div className={cx("ui-dropdown", className)} ref={containerRef}>
      <Button
        ref={triggerRef}
        variant={variant}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
      >
        {trigger}
        <ChevronDown aria-hidden="true" />
      </Button>
      {open ? (
        <div
          id={menuId}
          className={cx("ui-dropdown__menu", `ui-dropdown__menu--${align}`)}
          role="menu"
          aria-label={label}
          onKeyDown={handleMenuKeyDown}
        >
          {items.map((item, index) => (
            <button
              key={item.id}
              ref={(node) => { itemRefs.current[index] = node; }}
              type="button"
              role="menuitem"
              className={cx("ui-dropdown__item", item.destructive && "ui-dropdown__item--danger")}
              disabled={item.disabled}
              onClick={() => {
                item.onSelect();
                closeAndRestoreFocus();
              }}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
