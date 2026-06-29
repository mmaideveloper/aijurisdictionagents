// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { Navigation } from "../components/Navigation";

const mockSignOut = vi.fn();
const authState = vi.hoisted(() => ({ isAuthenticated: true, role: "user" }));

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    isAuthenticated: authState.isAuthenticated,
    user: {
      name: "Admin",
      email: "user@example.com",
      role: authState.role
    },
    signOut: mockSignOut
  })
}));

const labels: Record<string, string> = {
  appName: "AI Jurisdiction",
  tagline: "Agentic legal workspace",
  navHome: "Home",
  navNews: "News",
  navPricing: "Pricing",
  navAuth: "Log In",
  navApp: "App",
  navAssistant: "Assistant",
  navProfile: "Profile",
  navProfileMenu: "Profile menu",
  navMyProfile: "My Profile",
  navMyCases: "My Cases",
  navAdmin: "Admin",
  navLogOut: "Log Out"
};

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: (key: string) => labels[key] ?? key
  })
}));

vi.mock("../components/LanguageSwitcher", () => ({
  LanguageSwitcher: () => <div data-testid="language-switcher" />
}));

function renderNavigation({
  initialEntries = ["/"],
  isSidebarCollapsed = false
}: {
  initialEntries?: string[];
  isSidebarCollapsed?: boolean;
} = {}) {
  const PathIndicator = () => {
    const location = useLocation();
    return <div data-testid="current-path">{location.pathname}</div>;
  };

  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Navigation isSidebarCollapsed={isSidebarCollapsed} />
      <PathIndicator />
    </MemoryRouter>
  );
}

describe("Navigation profile actions", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockSignOut.mockReset();
    authState.isAuthenticated = true;
    authState.role = "user";
  });

  it("shows profile actions without opening a dropdown", () => {
    renderNavigation();

    expect(screen.getByText("Admin")).toBeDefined();
    expect(screen.getByText("user@example.com")).toBeDefined();
    expect(screen.getByRole("button", { name: "My Profile" })).toBeDefined();
    expect(screen.getByRole("button", { name: "My Cases" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Log Out" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Admin" })).toBeNull();
  });

  it("shows admin action for global admin users", () => {
    authState.role = "admin";
    renderNavigation();

    expect(screen.getByRole("button", { name: "Admin" })).toBeDefined();
  });

  it("navigates to /profile when My Profile is clicked", async () => {
    const user = userEvent.setup();
    renderNavigation();

    expect(screen.getByTestId("current-path").textContent).toBe("/");
    await user.click(screen.getByRole("button", { name: "My Profile" }));

    await waitFor(() => {
      expect(screen.getByTestId("current-path").textContent).toBe("/profile");
    });
  });

  it("navigates to / when My Cases is clicked", async () => {
    const user = userEvent.setup();
    renderNavigation({ initialEntries: ["/profile"] });

    expect(screen.getByTestId("current-path").textContent).toBe("/profile");
    await user.click(screen.getByRole("button", { name: "My Cases" }));

    await waitFor(() => {
      expect(screen.getByTestId("current-path").textContent).toBe("/");
    });
  });

  it("signs out from the visible profile action", async () => {
    const user = userEvent.setup();
    renderNavigation();

    await user.click(screen.getByRole("button", { name: "Log Out" }));
    expect(mockSignOut).toHaveBeenCalledTimes(1);
  });

  it("sends signed-in users to login after logout", async () => {
    const user = userEvent.setup();
    renderNavigation({ initialEntries: ["/profile"] });

    await user.click(screen.getByRole("button", { name: "Log Out" }));

    await waitFor(() => {
      expect(screen.getByTestId("current-path").textContent).toBe("/auth");
    });
  });

  it("shows login as the first menu item for signed-out users", () => {
    authState.isAuthenticated = false;

    const { container } = renderNavigation();

    const links = container.querySelectorAll(".nav-links a");
    expect(links[0]?.textContent).toBe("Log In");
  });

  it("shows the news route in the top menu", () => {
    renderNavigation({ initialEntries: ["/app"] });

    expect(screen.getByRole("link", { name: "News" }).getAttribute("href")).toBe("/aktuality");
  });

  it("does not show the assistant route for signed-in users", () => {
    renderNavigation({ initialEntries: ["/app"] });

    expect(screen.queryByRole("link", { name: "Assistant" })).toBeNull();
  });

  it("does not show the app route in the top menu", () => {
    renderNavigation({ initialEntries: ["/app"] });

    expect(screen.queryByRole("link", { name: "App" })).toBeNull();
  });

  it("shows navbar brand on non-home routes for signed-in users", () => {
    renderNavigation({ initialEntries: ["/app"] });

    expect(screen.getByText("AI Jurisdiction")).toBeDefined();
  });

  it("shows navbar brand on home when sidebar is collapsed", () => {
    renderNavigation({ initialEntries: ["/"], isSidebarCollapsed: true });

    expect(screen.getByText("AI Jurisdiction")).toBeDefined();
  });

  it("hides navbar brand on home when sidebar is expanded", () => {
    renderNavigation({ initialEntries: ["/"], isSidebarCollapsed: false });

    expect(screen.queryByText("AI Jurisdiction")).toBeNull();
  });
});
