import { describe, expect, it } from "vitest";

import { appRoutes, findRoute, routeList } from "./routes";

describe("typed application routes", () => {
  it("registers every approved UX-101 path exactly once", () => {
    expect(routeList.map((route) => route.path)).toEqual([
      "/overview",
      "/directory/users",
      "/directory/users/lookup",
      "/directory/groups",
      "/directory/org-units",
      "/gmail/delegations",
      "/settings/connections",
      "/administration/customers",
      "/administration/organizations",
      "/platform"
    ]);
    expect(new Set(routeList.map((route) => route.path)).size).toBe(routeList.length);
  });

  it("resolves only exact, non-sensitive screen routes", () => {
    expect(findRoute(appRoutes.users.path)?.id).toBe("users");
    expect(findRoute("/directory/users/albina@example.test")).toBeNull();
    expect(findRoute("/unknown")).toBeNull();
  });
});
