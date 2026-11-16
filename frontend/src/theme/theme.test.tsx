import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ACTIVE_THEME_STORAGE_KEY,
  applyAppearance,
  clearActiveThemeAccount,
  DEFAULT_DENSITY,
  DEFAULT_THEME,
  readAppearancePreference,
  storeDensityPreference,
  readThemePreference,
  storeThemePreference,
  useThemePreference
} from "./theme";

describe("theme preferences", () => {
  beforeEach(() => {
    window.localStorage.clear();
    applyAppearance({ theme: DEFAULT_THEME, density: DEFAULT_DENSITY });
  });

  afterEach(() => vi.restoreAllMocks());

  it("uses Navy & Teal when no valid preference exists", () => {
    expect(readThemePreference("user-a")).toBe("navy-teal");
    expect(document.documentElement.dataset.theme).toBe("navy-teal");
    expect(document.documentElement.dataset.density).toBe("comfortable");
  });

  it("persists theme and density independently for each opaque account", () => {
    storeThemePreference("private-user-id-a", "cobalt-ice");
    storeDensityPreference("private-user-id-a", "compact");
    storeDensityPreference("private-user-id-b", "comfortable");

    expect(readAppearancePreference("private-user-id-a")).toEqual({
      theme: "cobalt-ice",
      density: "compact"
    });
    expect(readAppearancePreference("private-user-id-b")).toEqual({
      theme: "navy-teal",
      density: "comfortable"
    });
  });

  it("migrates valid UX-104 theme-only records to comfortable density", () => {
    storeThemePreference("user-a", "graphite-copper");
    const accountKey = Array.from({ length: window.localStorage.length }, (_, index) =>
      window.localStorage.key(index)
    ).find((key) => key?.includes(".account."));
    const stored = JSON.parse(window.localStorage.getItem(accountKey!)!);
    window.localStorage.setItem(accountKey!, JSON.stringify({
      version: 1,
      account: stored.account,
      theme: stored.theme
    }));

    expect(readAppearancePreference("user-a")).toEqual({
      theme: "graphite-copper",
      density: "comfortable"
    });
  });

  it("persists preferences per opaque account without storing account identifiers", () => {
    storeThemePreference("private-user-id-a", "cobalt-ice");
    storeThemePreference("private-user-id-b", "graphite-copper");

    expect(readThemePreference("private-user-id-a")).toBe("cobalt-ice");
    expect(readThemePreference("private-user-id-b")).toBe("graphite-copper");
    const storageSnapshot = Array.from({ length: window.localStorage.length }, (_, index) => {
      const key = window.localStorage.key(index) ?? "";
      return `${key}:${window.localStorage.getItem(key) ?? ""}`;
    }).join("|");
    expect(storageSnapshot).not.toContain("private-user-id");
  });

  it("ignores corrupted storage and unavailable persistence", () => {
    storeThemePreference("user-a", "cobalt-ice");
    const accountKey = Array.from({ length: window.localStorage.length }, (_, index) =>
      window.localStorage.key(index)
    ).find((key) => key?.includes(".account."));
    expect(accountKey).toBeTruthy();
    window.localStorage.setItem(accountKey!, "not-json");
    expect(readThemePreference("user-a")).toBe(DEFAULT_THEME);

    window.localStorage.setItem(accountKey!, JSON.stringify({
      version: 2,
      account: "unexpected-account",
      theme: "cobalt-ice",
      density: "microscopic"
    }));
    expect(readAppearancePreference("user-a")).toEqual({
      theme: DEFAULT_THEME,
      density: DEFAULT_DENSITY
    });

    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    expect(() => storeThemePreference("user-a", "graphite-copper")).not.toThrow();
    expect(document.documentElement.dataset.theme).toBe("graphite-copper");
    expect(setItem).toHaveBeenCalled();
  });

  it("switches themes without remounting the preference owner", () => {
    const { result, rerender } = renderHook(
      ({ accountId }) => useThemePreference(accountId),
      { initialProps: { accountId: "user-a" as string | null } }
    );

    act(() => result.current.setTheme("cobalt-ice"));
    expect(result.current.theme).toBe("cobalt-ice");
    expect(document.documentElement.dataset.theme).toBe("cobalt-ice");

    act(() => result.current.setDensity("compact"));
    expect(result.current.density).toBe("compact");
    expect(document.documentElement.dataset.density).toBe("compact");

    rerender({ accountId: "user-b" });
    expect(result.current.theme).toBe("navy-teal");
    expect(result.current.density).toBe("comfortable");
    rerender({ accountId: "user-a" });
    expect(result.current.theme).toBe("cobalt-ice");
    expect(result.current.density).toBe("compact");
  });

  it("resets the active account theme on logout while retaining its private preference", () => {
    storeThemePreference("user-a", "graphite-copper");
    storeDensityPreference("user-a", "compact");
    clearActiveThemeAccount();
    expect(window.localStorage.getItem(ACTIVE_THEME_STORAGE_KEY)).toBeNull();
    expect(document.documentElement.dataset.theme).toBe("navy-teal");
    expect(document.documentElement.dataset.density).toBe("comfortable");
    expect(readAppearancePreference("user-a")).toEqual({
      theme: "graphite-copper",
      density: "compact"
    });
  });
});
