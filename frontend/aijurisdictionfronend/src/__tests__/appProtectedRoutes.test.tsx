// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "../App";

const authState = vi.hoisted(() => ({ isAuthenticated: false }));

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    isAuthenticated: authState.isAuthenticated
  })
}));

vi.mock("../components/PageLayout", () => ({
  PageLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>
}));

vi.mock("../auth/AuthCallbackView", () => ({
  default: () => <div>Auth Callback</div>
}));

vi.mock("../pages/Home", () => ({
  default: () => <div>Home Page</div>
}));

vi.mock("../pages/Auth", () => ({
  default: () => <div>Auth Page</div>
}));

vi.mock("../pages/Pricing", () => ({
  default: () => <div>Pricing Page</div>
}));

vi.mock("../pages/News", () => ({
  default: () => <div>News Page</div>
}));

vi.mock("../pages/AppDashboard", () => ({
  default: () => <div>App Dashboard</div>
}));

vi.mock("../pages/AssistantWorkspace", () => ({
  default: () => <div>Assistant Workspace</div>
}));

vi.mock("../pages/CaseIntake", () => ({
  default: () => <div>Case Intake</div>
}));

vi.mock("../pages/LawyerWorkspace", () => ({
  default: () => <div>Lawyer Workspace</div>
}));

vi.mock("../pages/AdviceSummary", () => ({
  default: () => <div>Advice Summary</div>
}));

vi.mock("../pages/Communication", () => ({
  default: () => <div>Communication</div>
}));

vi.mock("../pages/LawValidation", () => ({
  default: () => <div>Law Validation</div>
}));

vi.mock("../pages/LawRecommendation", () => ({
  default: () => <div>Law Recommendation</div>
}));

vi.mock("../pages/Profile", () => ({
  default: () => <div>Profile Page</div>
}));

vi.mock("../pages/Disclaimer", () => ({
  default: () => <div>Disclaimer</div>
}));

vi.mock("../pages/PrivacyPolicy", () => ({
  default: () => <div>Privacy</div>
}));

vi.mock("../pages/TermsOfService", () => ({
  default: () => <div>Terms</div>
}));

vi.mock("../pages/NotFound", () => ({
  default: () => <div>Not Found</div>
}));

describe("App protected routes", () => {
  afterEach(() => {
    cleanup();
  });

  it("renders the case workspace at /", () => {
    authState.isAuthenticated = true;

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Home Page")).toBeDefined();
    expect(screen.queryByText("Assistant Workspace")).toBeNull();
  });

  it("redirects unauthenticated users from /app to /auth", () => {
    authState.isAuthenticated = false;

    render(
      <MemoryRouter initialEntries={["/app"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Auth Page")).toBeDefined();
    expect(screen.queryByText("App Dashboard")).toBeNull();
  });

  it("redirects unauthenticated users from nested /app route to /auth", () => {
    authState.isAuthenticated = false;

    render(
      <MemoryRouter initialEntries={["/app/workspace"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Auth Page")).toBeDefined();
    expect(screen.queryByText("Lawyer Workspace")).toBeNull();
  });

  it("redirects unauthenticated users from /app/assistant to /auth", () => {
    authState.isAuthenticated = false;

    render(
      <MemoryRouter initialEntries={["/app/assistant"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Auth Page")).toBeDefined();
    expect(screen.queryByText("Assistant Workspace")).toBeNull();
  });

  it("redirects unauthenticated users from /profile to /auth", () => {
    authState.isAuthenticated = false;

    render(
      <MemoryRouter initialEntries={["/profile"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Auth Page")).toBeDefined();
    expect(screen.queryByText("Profile Page")).toBeNull();
  });

  it("allows unauthenticated users to access /aktuality", () => {
    authState.isAuthenticated = false;

    render(
      <MemoryRouter initialEntries={["/aktuality"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("News Page")).toBeDefined();
  });

  it("allows authenticated users to access /profile", () => {
    authState.isAuthenticated = true;

    render(
      <MemoryRouter initialEntries={["/profile"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Profile Page")).toBeDefined();
  });

  it("allows authenticated users to access /app/assistant", () => {
    authState.isAuthenticated = true;

    render(
      <MemoryRouter initialEntries={["/app/assistant"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Assistant Workspace")).toBeDefined();
  });
});
