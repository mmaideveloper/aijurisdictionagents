import React from "react";

export type CaseStatus = "In progress" | "On hold" | "Scheduled" | "Completed";
export type CaseMode = "Draft" | "Review" | "Live" | "Archive";
export type CaseRole =
  | "Compliance Counsel"
  | "Contract Analyst"
  | "Audit Strategist"
  | "Litigation Lead"
  | "General Counsel";

export type CaseInteraction = {
  id: string;
  createdAt: string;
  actor: string;
  message: string;
};

export type CaseWorkspace = {
  meta: string;
  objective: string;
  nextAction: string;
  jurisdiction: string;
  output: string;
};

export type CaseRecord = {
  id: string;
  title: string;
  description: string;
  status: CaseStatus;
  createdAt: string;
  interactionHistory: CaseInteraction[];
  selectedRole: CaseRole;
  selectedMode: CaseMode;
  workspace: CaseWorkspace;
};

type CaseContextValue = {
  cases: CaseRecord[];
  activeCaseId: string | null;
  activeCase: CaseRecord | null;
  createCase: () => CaseRecord;
  setActiveCase: (caseId: string) => void;
  updateCase: (caseId: string, update: Partial<CaseRecord>) => void;
  setCaseRole: (caseId: string, role: CaseRole) => void;
  setCaseMode: (caseId: string, mode: CaseMode) => void;
};

const CaseContext = React.createContext<CaseContextValue | undefined>(undefined);

const initialCases: CaseRecord[] = [
  {
    id: "case-001",
    title: "Keystone Holdings Intake",
    description: "Intake and jurisdiction review for Keystone Holdings matter.",
    status: "In progress",
    createdAt: "2026-02-03T09:00:00.000Z",
    interactionHistory: [
      {
        id: "case-001-1",
        createdAt: "2026-02-09T10:00:00.000Z",
        actor: "Compliance Counsel",
        message: "Drafted timeline summary from uploaded exhibits."
      },
      {
        id: "case-001-2",
        createdAt: "2026-02-10T12:30:00.000Z",
        actor: "Compliance Counsel",
        message: "Reviewed contract variance clauses for compliance risk."
      },
      {
        id: "case-001-3",
        createdAt: "2026-02-10T16:00:00.000Z",
        actor: "Compliance Counsel",
        message: "Queued agent sync with regional legal guidance."
      }
    ],
    selectedRole: "Compliance Counsel",
    selectedMode: "Draft",
    workspace: {
      meta: "Due in 2 days",
      objective: "Consolidate jurisdiction analysis and prepare a briefing memo for counsel review.",
      nextAction: "Schedule a 15-minute voice session with the AI agent to confirm scope.",
      jurisdiction: "EU + UK",
      output: "Briefing memo + checklist"
    }
  },
  {
    id: "case-002",
    title: "Atlas Contract Review",
    description: "Contract review and risk alignment for Atlas procurement.",
    status: "On hold",
    createdAt: "2026-01-28T14:15:00.000Z",
    interactionHistory: [
      {
        id: "case-002-1",
        createdAt: "2026-02-06T09:10:00.000Z",
        actor: "Contract Analyst",
        message: "Requested updated vendor packet from counsel."
      },
      {
        id: "case-002-2",
        createdAt: "2026-02-07T11:45:00.000Z",
        actor: "Contract Analyst",
        message: "Flagged missing data privacy addendum."
      },
      {
        id: "case-002-3",
        createdAt: "2026-02-08T15:20:00.000Z",
        actor: "Contract Analyst",
        message: "Prepared negotiation highlights for review."
      }
    ],
    selectedRole: "Contract Analyst",
    selectedMode: "Review",
    workspace: {
      meta: "Waiting on docs",
      objective: "Gather missing vendor exhibits and align on scope with procurement leadership.",
      nextAction: "Follow up with counsel on outstanding document set.",
      jurisdiction: "US + Canada",
      output: "Clause redline + risk summary"
    }
  },
  {
    id: "case-003",
    title: "Meridian Audit Prep",
    description: "Audit preparation for Meridian controls validation.",
    status: "Scheduled",
    createdAt: "2026-02-05T08:30:00.000Z",
    interactionHistory: [
      {
        id: "case-003-1",
        createdAt: "2026-02-10T08:45:00.000Z",
        actor: "Audit Strategist",
        message: "Outlined audit scope with finance partners."
      },
      {
        id: "case-003-2",
        createdAt: "2026-02-10T13:05:00.000Z",
        actor: "Audit Strategist",
        message: "Mapped evidence checklist to control owners."
      },
      {
        id: "case-003-3",
        createdAt: "2026-02-10T17:30:00.000Z",
        actor: "Audit Strategist",
        message: "Drafted opening statement for kickoff."
      }
    ],
    selectedRole: "Audit Strategist",
    selectedMode: "Live",
    workspace: {
      meta: "Kickoff today",
      objective: "Align audit prep checklist and confirm timeline with internal teams.",
      nextAction: "Start kickoff session and capture action items.",
      jurisdiction: "EU + US",
      output: "Audit kickoff deck"
    }
  },
  {
    id: "case-004",
    title: "Northwind Arbitration",
    description: "Post-arbitration wrap-up and archive for Northwind.",
    status: "Completed",
    createdAt: "2026-01-12T16:20:00.000Z",
    interactionHistory: [
      {
        id: "case-004-1",
        createdAt: "2026-02-04T09:00:00.000Z",
        actor: "Litigation Lead",
        message: "Generated final arbitration brief."
      },
      {
        id: "case-004-2",
        createdAt: "2026-02-04T12:20:00.000Z",
        actor: "Litigation Lead",
        message: "Collected final stakeholder sign-offs."
      },
      {
        id: "case-004-3",
        createdAt: "2026-02-04T16:05:00.000Z",
        actor: "Litigation Lead",
        message: "Archived evidence package."
      }
    ],
    selectedRole: "Litigation Lead",
    selectedMode: "Archive",
    workspace: {
      meta: "Closed last week",
      objective: "Finalize arbitration summary and archive case documentation.",
      nextAction: "Send closing memo to executive stakeholders.",
      jurisdiction: "UK",
      output: "Arbitration summary pack"
    }
  }
];

const buildNewCase = (index: number): CaseRecord => {
  const createdAt = new Date().toISOString();
  const idBase = Date.now().toString();
  return {
    id: `case-${idBase}`,
    title: `New matter ${index + 1}`,
    description: "Newly created case workspace.",
    status: "In progress",
    createdAt,
    interactionHistory: [
      {
        id: `case-${idBase}-1`,
        createdAt,
        actor: "General Counsel",
        message: "Opened new case workspace."
      },
      {
        id: `case-${idBase}-2`,
        createdAt,
        actor: "General Counsel",
        message: "Set initial jurisdiction focus."
      }
    ],
    selectedRole: "General Counsel",
    selectedMode: "Draft",
    workspace: {
      meta: "Just created",
      objective: "Define scope, assign roles, and request initial documents.",
      nextAction: "Add key facts and upload first evidence set.",
      jurisdiction: "TBD",
      output: "Intake brief"
    }
  };
};

export const CaseProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [cases, setCases] = React.useState<CaseRecord[]>(initialCases);
  const [activeCaseId, setActiveCaseId] = React.useState<string | null>(initialCases[0]?.id ?? null);

  const activeCase = React.useMemo(() => {
    return cases.find((caseItem) => caseItem.id === activeCaseId) ?? cases[0] ?? null;
  }, [activeCaseId, cases]);

  const createCase = React.useCallback(() => {
    const newCase = buildNewCase(cases.length);
    setCases((prev) => [newCase, ...prev]);
    setActiveCaseId(newCase.id);
    return newCase;
  }, [cases.length]);

  const setActiveCase = React.useCallback((caseId: string) => {
    setActiveCaseId(caseId);
  }, []);

  const updateCase = React.useCallback((caseId: string, update: Partial<CaseRecord>) => {
    setCases((prev) =>
      prev.map((caseItem) => (caseItem.id === caseId ? { ...caseItem, ...update } : caseItem))
    );
  }, []);

  const setCaseRole = React.useCallback((caseId: string, role: CaseRole) => {
    updateCase(caseId, { selectedRole: role });
  }, [updateCase]);

  const setCaseMode = React.useCallback((caseId: string, mode: CaseMode) => {
    updateCase(caseId, { selectedMode: mode });
  }, [updateCase]);

  const value = React.useMemo(
    () => ({
      cases,
      activeCaseId,
      activeCase,
      createCase,
      setActiveCase,
      updateCase,
      setCaseRole,
      setCaseMode
    }),
    [cases, activeCaseId, activeCase, createCase, setActiveCase, updateCase, setCaseRole, setCaseMode]
  );

  return <CaseContext.Provider value={value}>{children}</CaseContext.Provider>;
};

export const useCases = () => {
  const context = React.useContext(CaseContext);
  if (!context) {
    throw new Error("useCases must be used within a CaseProvider.");
  }
  return context;
};
