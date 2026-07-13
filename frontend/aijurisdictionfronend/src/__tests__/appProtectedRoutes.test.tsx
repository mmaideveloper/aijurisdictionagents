// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, vi, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import App from "../App";
import { PRODUCT_NAMES } from "../branding";

const authState = vi.hoisted(() => ({ isAuthenticated: false, role: "user" }));

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    isAuthenticated: authState.isAuthenticated,
    user: { role: authState.role }
  })
}));

vi.mock("../components/PageLayout", () => ({
  PageLayout: ({ children }: { children: React.ReactNode }) => <>{children}</>
}));

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: (key: string) => (key === "appName" ? PRODUCT_NAMES.sk : key)
  })
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

vi.mock("../pages/AIModelAdmin", () => ({
  default: () => <div>Admin Page</div>
}));

vi.mock("../pages/DocumentViewer", () => ({
  default: () => <div>Document Viewer</div>
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
    vi.unstubAllGlobals();
    authState.role = "user";
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

  it("keeps the product title after client-side navigation to the assistant", async () => {
    authState.isAuthenticated = true;
    const user = userEvent.setup();
    const NavigateToAssistant = () => {
      const navigate = useNavigate();
      return <button onClick={() => navigate("/app/assistant")}>Open assistant</button>;
    };

    render(
      <MemoryRouter initialEntries={["/app"]}>
        <NavigateToAssistant />
        <App />
      </MemoryRouter>
    );

    expect(document.title).toBe(PRODUCT_NAMES.sk);
    document.title = "Legacy title";
    await user.click(screen.getByRole("button", { name: "Open assistant" }));

    expect(await screen.findByText("Assistant Workspace")).toBeDefined();
    expect(document.title).toBe(PRODUCT_NAMES.sk);
  });

  it("renders the assistant workspace at / on agent.jurisdigta.eu for authenticated users", () => {
    authState.isAuthenticated = true;
    vi.stubGlobal("location", { hostname: "agent.jurisdigta.eu" });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Assistant Workspace")).toBeDefined();
    expect(screen.queryByText("Home Page")).toBeNull();
  });

  it("redirects unauthenticated users from / on agent.jurisdigta.eu to /auth", () => {
    authState.isAuthenticated = false;
    vi.stubGlobal("location", { hostname: "agent.jurisdigta.eu" });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Auth Page")).toBeDefined();
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

  it("redirects unauthenticated users from case deep links to /auth", () => {
    authState.isAuthenticated = false;

    render(
      <MemoryRouter initialEntries={["/case/case-1"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Auth Page")).toBeDefined();
    expect(screen.queryByText("Assistant Workspace")).toBeNull();
  });

  it("redirects unauthenticated users from /app/chat to /auth", () => {
    authState.isAuthenticated = false;

    render(
      <MemoryRouter initialEntries={["/app/chat"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Auth Page")).toBeDefined();
    expect(screen.queryByText("Home Page")).toBeNull();
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

  it("allows document viewer links to open without redirecting to auth", () => {
    authState.isAuthenticated = false;

    render(
      <MemoryRouter initialEntries={["/app/documents/view?caseId=case-1&docId=doc-1&userId=user-1"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Document Viewer")).toBeDefined();
    expect(screen.queryByText("Auth Page")).toBeNull();
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

  it("allows authenticated users to open case deep links in the assistant", () => {
    authState.isAuthenticated = true;

    render(
      <MemoryRouter initialEntries={["/case/case-1"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Assistant Workspace")).toBeDefined();
  });

  it("redirects authenticated non-admin users from /app/admin", () => {
    authState.isAuthenticated = true;
    authState.role = "user";

    render(
      <MemoryRouter initialEntries={["/app/admin"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Home Page")).toBeDefined();
    expect(screen.queryByText("Admin Page")).toBeNull();
  });

  it("allows global admin users to access /app/admin", () => {
    authState.isAuthenticated = true;
    authState.role = "admin";

    render(
      <MemoryRouter initialEntries={["/app/admin"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Admin Page")).toBeDefined();
  });

  it("keeps /app/chat as an authenticated assistant workspace alias", () => {
    authState.isAuthenticated = true;

    render(
      <MemoryRouter initialEntries={["/app/chat"]}>
        <App />
      </MemoryRouter>
    );

    expect(screen.getByText("Assistant Workspace")).toBeDefined();
  });
});
