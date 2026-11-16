import { useCallback, useEffect, useState } from "react";

export const THEME_IDS = ["navy-teal", "cobalt-ice", "graphite-copper"] as const;
export const DENSITY_IDS = ["comfortable", "compact"] as const;

export type ThemeId = (typeof THEME_IDS)[number];
export type DensityId = (typeof DENSITY_IDS)[number];

export const DEFAULT_THEME: ThemeId = "navy-teal";
export const DEFAULT_DENSITY: DensityId = "comfortable";
export const ACTIVE_THEME_STORAGE_KEY = "wgasuite.ui.theme.active.v1";
const THEME_STORAGE_PREFIX = "wgasuite.ui.theme.account.v1";

interface StoredAppearancePreference {
  version: 2;
  account: string;
  theme: ThemeId;
  density: DensityId;
}

interface LegacyThemePreference {
  version: 1;
  account: string;
  theme: ThemeId;
}

export interface AppearancePreference {
  theme: ThemeId;
  density: DensityId;
}

export const THEME_OPTIONS: ReadonlyArray<{ id: ThemeId; label: string; description: string }> = [
  { id: "navy-teal", label: "Navy & Teal", description: "WGASuite default" },
  { id: "cobalt-ice", label: "Cobalt & Ice", description: "Light and airy" },
  { id: "graphite-copper", label: "Graphite & Copper", description: "Premium dark" }
];

export const DENSITY_OPTIONS: ReadonlyArray<{ id: DensityId; label: string; description: string }> = [
  { id: "comfortable", label: "Comfortable", description: "More room around controls" },
  { id: "compact", label: "Compact", description: "More information on screen" }
];

export function isThemeId(value: unknown): value is ThemeId {
  return typeof value === "string" && THEME_IDS.includes(value as ThemeId);
}

export function isDensityId(value: unknown): value is DensityId {
  return typeof value === "string" && DENSITY_IDS.includes(value as DensityId);
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

function readStoredPreference(key: string): StoredAppearancePreference | LegacyThemePreference | null {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (typeof parsed.account !== "string" || !isThemeId(parsed.theme)) return null;
    if (parsed.version === 1) return parsed as unknown as LegacyThemePreference;
    if (parsed.version !== 2 || !isDensityId(parsed.density)) return null;
    return parsed as unknown as StoredAppearancePreference;
  } catch {
    return null;
  }
}

function normalizePreference(
  preference: StoredAppearancePreference | LegacyThemePreference | null
): AppearancePreference {
  return {
    theme: preference?.theme ?? DEFAULT_THEME,
    density: preference?.version === 2 ? preference.density : DEFAULT_DENSITY
  };
}

export function readAppearancePreference(accountId: string): AppearancePreference {
  const account = accountStorageId(accountId);
  const preference = readStoredPreference(preferenceKey(account));
  return preference?.account === account
    ? normalizePreference(preference)
    : { theme: DEFAULT_THEME, density: DEFAULT_DENSITY };
}

export function readThemePreference(accountId: string): ThemeId {
  return readAppearancePreference(accountId).theme;
}

export function applyAppearance({ theme, density }: AppearancePreference): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.density = density;
  document.documentElement.style.colorScheme = theme === "graphite-copper" ? "dark" : "light";
}

export function applyTheme(theme: ThemeId): void {
  applyAppearance({ theme, density: readAppliedDensity() });
}

function storeAppearancePreference(accountId: string, preference: AppearancePreference): void {
  const account = accountStorageId(accountId);
  const stored: StoredAppearancePreference = { version: 2, account, ...preference };
  applyAppearance(preference);
  try {
    const serialized = JSON.stringify(stored);
    window.localStorage.setItem(preferenceKey(account), serialized);
    window.localStorage.setItem(ACTIVE_THEME_STORAGE_KEY, serialized);
  } catch {
    // The applied appearance still works when hardened browser settings block persistence.
  }
}

export function storeThemePreference(accountId: string, theme: ThemeId): void {
  const current = readAppearancePreference(accountId);
  storeAppearancePreference(accountId, { ...current, theme });
}

export function storeDensityPreference(accountId: string, density: DensityId): void {
  const current = readAppearancePreference(accountId);
  storeAppearancePreference(accountId, { ...current, density });
}

export function clearActiveThemeAccount(): void {
  try {
    window.localStorage.removeItem(ACTIVE_THEME_STORAGE_KEY);
  } catch {
    // Storage may be unavailable; resetting the document appearance remains safe.
  }
  applyAppearance({ theme: DEFAULT_THEME, density: DEFAULT_DENSITY });
}

export function readAppliedTheme(): ThemeId {
  const value = document.documentElement.dataset.theme;
  return isThemeId(value) ? value : DEFAULT_THEME;
}

export function readAppliedDensity(): DensityId {
  const value = document.documentElement.dataset.density;
  return isDensityId(value) ? value : DEFAULT_DENSITY;
}

export function useThemePreference(accountId: string | null) {
  const [theme, setThemeState] = useState<ThemeId>(() => readAppliedTheme());
  const [density, setDensityState] = useState<DensityId>(() => readAppliedDensity());

  const activateAccountTheme = useCallback((nextAccountId: string) => {
    const next = readAppearancePreference(nextAccountId);
    applyAppearance(next);
    setThemeState(next.theme);
    setDensityState(next.density);
  }, []);

  useEffect(() => {
    if (accountId) activateAccountTheme(accountId);
  }, [accountId, activateAccountTheme]);

  const setTheme = useCallback(
    (nextTheme: ThemeId) => {
      setThemeState(nextTheme);
      const next = { theme: nextTheme, density };
      if (accountId) storeAppearancePreference(accountId, next);
      else applyAppearance(next);
    },
    [accountId, density]
  );

  const setDensity = useCallback(
    (nextDensity: DensityId) => {
      setDensityState(nextDensity);
      const next = { theme, density: nextDensity };
      if (accountId) storeAppearancePreference(accountId, next);
      else applyAppearance(next);
    },
    [accountId, theme]
  );

  const resetThemeSession = useCallback(() => {
    clearActiveThemeAccount();
    setThemeState(DEFAULT_THEME);
    setDensityState(DEFAULT_DENSITY);
  }, []);

  return {
    theme,
    density,
    setTheme,
    setDensity,
    activateAccountTheme,
    resetThemeSession
  };
}
