// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { PageLayout } from "../components/PageLayout";

vi.mock("../components/Navigation", () => ({
  Navigation: ({ isSidebarCollapsed }: { isSidebarCollapsed?: boolean }) => (
    <div>Navigation {isSidebarCollapsed ? "collapsed" : "expanded"}</div>
  )
}));

vi.mock("../components/Sidebar", () => ({
  Sidebar: () => <aside>Case sidebar</aside>
}));

vi.mock("../components/Footer", () => ({
  Footer: () => <footer>Public footer</footer>
}));

vi.mock("../routing", () => ({
  isAgentHost: () => false
}));

describe("PageLayout", () => {
  afterEach(cleanup);

  it("uses the assistant chrome for an authenticated case deep link", () => {
    render(
      <MemoryRouter initialEntries={["/case/case-123"]}>
        <PageLayout>
          <div>Case workspace</div>
        </PageLayout>
      </MemoryRouter>
    );

    expect(screen.getByText("Navigation collapsed")).toBeDefined();
    expect(screen.getByText("Case sidebar")).toBeDefined();
    expect(screen.getByText("Case workspace")).toBeDefined();
    expect(screen.queryByText("Public footer")).toBeNull();
  });

  it("keeps public pages outside the case namespace on the public layout", () => {
    render(
      <MemoryRouter initialEntries={["/pricing"]}>
        <PageLayout>
          <div>Pricing content</div>
        </PageLayout>
      </MemoryRouter>
    );

    expect(screen.getByText("Navigation expanded")).toBeDefined();
    expect(screen.queryByText("Case sidebar")).toBeNull();
    expect(screen.getByText("Public footer")).toBeDefined();
  });
});
