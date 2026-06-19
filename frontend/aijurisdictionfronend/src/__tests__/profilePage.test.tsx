// @vitest-environment jsdom

import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Profile from "../pages/Profile";

vi.mock("../auth/webAuth", () => ({
  useAuth: () => ({
    user: {
      firstName: "Admin",
      lastName: "User",
      email: "user@example.com",
      role: "JurisDigta user",
      name: "Admin User"
    }
  })
}));

vi.mock("../state/CaseProvider", () => ({
  useCases: () => ({
    cases: [
      {
        id: "case-1",
        title: "Keystone Holdings Intake",
        status: "In progress"
      }
    ],
    documents: [
      {
        id: "doc-1",
        originalFilename: "keystone-timeline.pdf",
        caseTitle: "Keystone Holdings Intake",
        sizeLabel: "178 KB"
      }
    ],
    selectCase: vi.fn()
  })
}));

const labels: Record<string, string> = {
  profileTitle: "My Profile",
  profileSubtitle: "Review account details stored in your workspace session.",
  profileOverviewTitle: "Session profile",
  profileOverviewBody: "This data is loaded from the current API-authenticated user.",
  profileDetailsTitle: "User details",
  profileFieldFirstName: "First Name",
  profileFieldLastName: "Last Name",
  profileFieldEmail: "Email",
  profileFieldRole: "Role",
  profileFieldAccountCreated: "Account Created Date",
  profileOpenedCasesTitle: "Opened cases",
  profileOpenedCasesSubtitle: "Jump back into active matters from your profile.",
  profileOpenedCasesEmpty: "No opened cases yet.",
  profileDocumentsTitle: "My Documents",
  profileDocumentsSubtitle: "Uploaded documents from your case intake flow.",
  profileDocumentsEmpty: "No uploaded documents yet.",
  profileDocumentCaseLabel: "Case",
  profileBilling: "Billing cadence",
  pricingMonthly: "Monthly",
  pricingYearly: "Yearly",
  profileCadenceCurrent: "Current cadence",
  profilePlan: "Subscription tier",
  profilePlanSelected: "Selected",
  planFreeName: "Free",
  profileOptionalPending: "Coming soon",
  profileNotAvailable: "Not available"
};

vi.mock("../components/LanguageProvider", () => ({
  useLanguage: () => ({
    t: (key: string) => labels[key] ?? key
  })
}));

describe("Profile page", () => {
  it("renders structured user info from API auth state", () => {
    render(
      <MemoryRouter>
        <Profile />
      </MemoryRouter>
    );

    expect(screen.getByText("My Profile")).toBeDefined();
    expect(screen.getByText("First Name")).toBeDefined();
    expect(screen.getByText("Admin")).toBeDefined();
    expect(screen.getByText("Last Name")).toBeDefined();
    expect(screen.getByText("User")).toBeDefined();
    expect(screen.getByText("Email")).toBeDefined();
    expect(screen.getByText("user@example.com")).toBeDefined();
    expect(screen.getByText("Role")).toBeDefined();
    expect(screen.getByText("JurisDigta user")).toBeDefined();
    expect(screen.getByText("Account Created Date")).toBeDefined();
    expect(screen.getByText("Billing cadence")).toBeDefined();
    expect(screen.getByText("Opened cases")).toBeDefined();
    expect(screen.getByText("Keystone Holdings Intake")).toBeDefined();
    expect(screen.getByText("My Documents")).toBeDefined();
    expect(screen.getByText("keystone-timeline.pdf")).toBeDefined();
    expect(screen.getByText("Case: Keystone Holdings Intake")).toBeDefined();
  });
});
