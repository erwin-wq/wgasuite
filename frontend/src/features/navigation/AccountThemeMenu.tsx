import { Check, ChevronDown, LogOut, Palette, UserRound } from "lucide-react";
import { type KeyboardEvent, useEffect, useRef, useState } from "react";

import { Button } from "../../components/ui/Button";
import { THEME_OPTIONS, type ThemeId } from "../../theme/theme";

interface AccountThemeMenuProps {
  fullName: string;
  role: string;
  theme: ThemeId;
  onThemeChange: (theme: ThemeId) => void;
  onLogout: () => void;
}

export function AccountThemeMenu({
  fullName,
  role,
  theme,
  onThemeChange,
  onLogout
}: AccountThemeMenuProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!isOpen) return;
    itemRefs.current.find((item) => item?.dataset.themeId === theme)?.focus();

    function closeOnOutsideClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setIsOpen(false);
    }
    function closeOnEscape(event: globalThis.KeyboardEvent) {
      if (event.key !== "Escape") return;
      setIsOpen(false);
      triggerRef.current?.focus();
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutsideClick);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isOpen, theme]);

  function handleMenuKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp" && event.key !== "Home" && event.key !== "End") return;
    event.preventDefault();
    const enabled = itemRefs.current.filter((item): item is HTMLButtonElement => Boolean(item));
    if (!enabled.length) return;
    const current = enabled.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "Home"
      ? 0
      : event.key === "End"
        ? enabled.length - 1
        : (current + (event.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length;
    enabled[next]?.focus();
  }

  return (
    <div className="account-menu" ref={containerRef}>
      <Button
        ref={triggerRef}
        variant="secondary"
        size="sm"
        className="account-menu-trigger"
        aria-label={`Account and appearance for ${fullName}`}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-controls={isOpen ? "account-theme-menu" : undefined}
        onClick={() => setIsOpen((current) => !current)}
      >
        <UserRound aria-hidden="true" />
        <span className="account-summary">
          <span>{fullName}</span>
          <small>{role.replace(/_/g, " ")}</small>
        </span>
        <ChevronDown aria-hidden="true" />
      </Button>

      {isOpen ? (
        <div
          id="account-theme-menu"
          className="account-menu-panel"
          role="menu"
          aria-label="Account and appearance"
          onKeyDown={handleMenuKeyDown}
        >
          <div className="account-menu-heading">
            <Palette aria-hidden="true" />
            <span>Theme</span>
          </div>
          <div className="theme-menu-options" role="group" aria-label="Application theme">
            {THEME_OPTIONS.map((option, index) => (
              <button
                key={option.id}
                ref={(node) => { itemRefs.current[index] = node; }}
                type="button"
                role="menuitemradio"
                aria-checked={theme === option.id}
                data-theme-id={option.id}
                className="theme-menu-option"
                onClick={() => onThemeChange(option.id)}
              >
                <span className={`theme-swatch theme-swatch--${option.id}`} aria-hidden="true" />
                <span>
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </span>
                {theme === option.id ? <Check aria-hidden="true" /> : null}
              </button>
            ))}
          </div>
          <div className="account-menu-divider" />
          <button
            ref={(node) => { itemRefs.current[THEME_OPTIONS.length] = node; }}
            type="button"
            role="menuitem"
            className="account-menu-logout"
            onClick={() => {
              setIsOpen(false);
              onLogout();
            }}
          >
            <LogOut aria-hidden="true" />
            <span>Logout</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
