import { useCallback, useEffect, useState } from "react";

export const THEME_IDS = ["navy-teal", "cobalt-ice", "graphite-copper"] as const;

export type ThemeId = (typeof THEME_IDS)[number];

export const DEFAULT_THEME: ThemeId = "navy-teal";
export const ACTIVE_THEME_STORAGE_KEY = "wgasuite.ui.theme.active.v1";
const THEME_STORAGE_PREFIX = "wgasuite.ui.theme.account.v1";

interface StoredThemePreference {
  version: 1;
  account: string;
  theme: ThemeId;
}

export const THEME_OPTIONS: ReadonlyArray<{ id: ThemeId; label: string; description: string }> = [
  { id: "navy-teal", label: "Navy & Teal", description: "WGASuite default" },
  { id: "cobalt-ice", label: "Cobalt & Ice", description: "Light and airy" },
  { id: "graphite-copper", label: "Graphite & Copper", description: "Premium dark" }
];

export function isThemeId(value: unknown): value is ThemeId {
  return typeof value === "string" && THEME_IDS.includes(value as ThemeId);
}

function accountStorageId(accountId: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < accountId.length; index += 1) {
    hash ^= accountId.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36);
}

function preferenceKey(account: string): string {
  return `${THEME_STORAGE_PREFIX}.${account}`;
}

function readStoredPreference(key: string): StoredThemePreference | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredThemePreference>;
    if (parsed.version !== 1 || typeof parsed.account !== "string" || !isThemeId(parsed.theme)) {
      return null;
    }
    return parsed as StoredThemePreference;
  } catch {
    return null;
  }
}

export function readThemePreference(accountId: string): ThemeId {
  const account = accountStorageId(accountId);
  const preference = readStoredPreference(preferenceKey(account));
  return preference?.account === account ? preference.theme : DEFAULT_THEME;
}

export function applyTheme(theme: ThemeId): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme === "graphite-copper" ? "dark" : "light";
}

export function storeThemePreference(accountId: string, theme: ThemeId): void {
  const account = accountStorageId(accountId);
  const preference: StoredThemePreference = { version: 1, account, theme };
  applyTheme(theme);
  try {
    const serialized = JSON.stringify(preference);
    window.localStorage.setItem(preferenceKey(account), serialized);
    window.localStorage.setItem(ACTIVE_THEME_STORAGE_KEY, serialized);
  } catch {
    // The applied theme still works when hardened browser settings block persistence.
  }
}

export function clearActiveThemeAccount(): void {
  try {
    window.localStorage.removeItem(ACTIVE_THEME_STORAGE_KEY);
  } catch {
    // Storage may be unavailable; resetting the document theme remains safe.
  }
  applyTheme(DEFAULT_THEME);
}

export function readAppliedTheme(): ThemeId {
  const value = document.documentElement.dataset.theme;
  return isThemeId(value) ? value : DEFAULT_THEME;
}

export function useThemePreference(accountId: string | null) {
  const [theme, setThemeState] = useState<ThemeId>(() => readAppliedTheme());

  useEffect(() => {
    if (!accountId) return;
    const nextTheme = readThemePreference(accountId);
    applyTheme(nextTheme);
    setThemeState(nextTheme);
  }, [accountId]);

  const setTheme = useCallback(
    (nextTheme: ThemeId) => {
      setThemeState(nextTheme);
      if (accountId) storeThemePreference(accountId, nextTheme);
      else applyTheme(nextTheme);
    },
    [accountId]
  );

  const activateAccountTheme = useCallback((nextAccountId: string) => {
    const nextTheme = readThemePreference(nextAccountId);
    applyTheme(nextTheme);
    setThemeState(nextTheme);
  }, []);

  const resetThemeSession = useCallback(() => {
    clearActiveThemeAccount();
    setThemeState(DEFAULT_THEME);
  }, []);

  return { theme, setTheme, activateAccountTheme, resetThemeSession };
}
