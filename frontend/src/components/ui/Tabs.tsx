import { type KeyboardEvent, type ReactNode, useRef } from "react";

import { cx } from "./utils";

export interface TabItem {
  id: string;
  label: string;
  icon?: ReactNode;
  disabled?: boolean;
  controls?: string;
}

export interface TabsProps {
  items: readonly TabItem[];
  activeId: string;
  onChange: (id: string) => void;
  ariaLabel: string;
  className?: string;
}

export function Tabs({ items, activeId, onChange, ariaLabel, className }: TabsProps) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  function moveFocus(currentIndex: number, direction: 1 | -1) {
    for (let step = 1; step <= items.length; step += 1) {
      const nextIndex = (currentIndex + direction * step + items.length) % items.length;
      if (!items[nextIndex]?.disabled) {
        refs.current[nextIndex]?.focus();
        return;
      }
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      moveFocus(index, 1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      moveFocus(index, -1);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      const candidates = event.key === "Home" ? items : [...items].reverse();
      const target = candidates.find((item) => !item.disabled);
      const targetIndex = target ? items.findIndex((item) => item.id === target.id) : -1;
      if (targetIndex >= 0) refs.current[targetIndex]?.focus();
    }
  }

  return (
    <div className={cx("ui-tabs", className)} role="tablist" aria-label={ariaLabel}>
      {items.map((item, index) => (
        <button
          key={item.id}
          ref={(node) => { refs.current[index] = node; }}
          type="button"
          role="tab"
          className="ui-tabs__tab"
          aria-selected={activeId === item.id}
          aria-controls={item.controls}
          tabIndex={activeId === item.id ? 0 : -1}
          disabled={item.disabled}
          onClick={() => onChange(item.id)}
          onKeyDown={(event) => handleKeyDown(event, index)}
        >
          {item.icon}
          <span>{item.label}</span>
        </button>
      ))}
    </div>
  );
}
