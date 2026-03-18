// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { Navigation } from "../components/Navigation";

const mockSignOut = vi.fn();

vi.mock("../auth/mockAuth", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    user: {
      name: "Admin",
      email: "admin@admin.com"
    },
    signOut: mockSignOut
  })
}));

const labels: Record<string, string> = {
  navHome: "Home",
  navPricing: "Pricing",
  navApp: "App",
  navProfile: "Profile",
  navProfileMenu: "Profile menu",
  navMyProfile: "My Profile",
  navMyCases: "My Cases",
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

function renderNavigation() {
  const PathIndicator = () => {
    const location = useLocation();
    return <div data-testid="current-path">{location.pathname}</div>;
  };

  return render(
    <MemoryRouter>
      <Navigation />
      <PathIndicator />
    </MemoryRouter>
  );
}

describe("Navigation profile dropdown", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    mockSignOut.mockReset();
  });

  it("opens on profile trigger click with expected options", async () => {
    const user = userEvent.setup();
    renderNavigation();

    await user.click(screen.getByLabelText("Profile"));

    expect(screen.getByRole("menu", { name: "Profile menu" })).toBeDefined();
    expect(screen.getByRole("menuitem", { name: "My Profile" })).toBeDefined();
    expect(screen.getByRole("menuitem", { name: "My Cases" })).toBeDefined();
    expect(screen.getByRole("menuitem", { name: "Log Out" })).toBeDefined();
  });

  it("closes on outside click", async () => {
    const user = userEvent.setup();
    renderNavigation();

    await user.click(screen.getByLabelText("Profile"));
    expect(screen.getByRole("menu", { name: "Profile menu" })).toBeDefined();

    fireEvent.mouseDown(document.body);

    await waitFor(() => {
      expect(screen.queryByRole("menu", { name: "Profile menu" })).toBeNull();
    });
  });

  it("closes on escape key press", async () => {
    const user = userEvent.setup();
    renderNavigation();

    await user.click(screen.getByLabelText("Profile"));
    expect(screen.getByRole("menu", { name: "Profile menu" })).toBeDefined();

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => {
      expect(screen.queryByRole("menu", { name: "Profile menu" })).toBeNull();
    });
  });

  it("supports keyboard navigation and closes when menu option is clicked", async () => {
    const user = userEvent.setup();
    renderNavigation();

    const trigger = screen.getByLabelText("Profile");
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    const menu = await screen.findByRole("menu", { name: "Profile menu" });
    await waitFor(() => {
      expect(document.activeElement?.textContent).toBe("My Profile");
    });

    fireEvent.keyDown(menu, { key: "ArrowDown" });
    await waitFor(() => {
      expect(document.activeElement?.textContent).toBe("My Cases");
    });

    await user.click(screen.getByRole("menuitem", { name: "Log Out" }));
    expect(mockSignOut).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu", { name: "Profile menu" })).toBeNull();
  });

  it("navigates to /profile when My Profile is clicked", async () => {
    const user = userEvent.setup();
    renderNavigation();

    expect(screen.getByTestId("current-path").textContent).toBe("/");
    await user.click(screen.getByLabelText("Profile"));
    await user.click(screen.getByRole("menuitem", { name: "My Profile" }));

    await waitFor(() => {
      expect(screen.getByTestId("current-path").textContent).toBe("/profile");
    });
  });
});
