import { Language } from "../data/translations";

export type SeededCaseTemplateId = "case-001" | "case-002" | "case-003" | "case-004";

type MockCaseTemplate = {
  title: string;
  description: string;
  meta: string;
  objective: string;
  nextAction: string;
  output: string;
};

const templates: Record<Language, Record<SeededCaseTemplateId, MockCaseTemplate>> = {
  en: {
    "case-001": {
      title: "Keystone Holdings Intake",
      description: "EU + UK matter involving Northshore Advisory.",
      meta: "Due in 2 days",
      objective: "Consolidate jurisdiction analysis and prepare a briefing memo for counsel review.",
      nextAction: "Schedule a 15-minute voice session with the AI agent to confirm scope.",
      output: "Briefing memo + checklist"
    },
    "case-002": {
      title: "Atlas Contract Review",
      description: "US + Canada matter involving Atlas Procurement Vendor.",
      meta: "Waiting on docs",
      objective: "Gather missing vendor exhibits and align on scope with procurement leadership.",
      nextAction: "Follow up with counsel on outstanding document set.",
      output: "Clause redline + risk summary"
    },
    "case-003": {
      title: "Meridian Audit Prep",
      description: "EU + US matter involving External Audit Team.",
      meta: "Kickoff today",
      objective: "Align audit prep checklist and confirm timeline with internal teams.",
      nextAction: "Start kickoff session and capture action items.",
      output: "Audit kickoff deck"
    },
    "case-004": {
      title: "Northwind Arbitration",
      description: "UK matter involving Northwind Counterparty.",
      meta: "Closed last week",
      objective: "Finalize arbitration summary and archive case documentation.",
      nextAction: "Send closing memo to executive stakeholders.",
      output: "Arbitration summary pack"
    }
  },
  sk: {
    "case-001": {
      title: "Intake Keystone Holdings",
      description: "Prípad EÚ + UK proti Northshore Advisory.",
      meta: "Termín o 2 dni",
      objective: "Konsolidujte jurisdikčnú analýzu a pripravte briefing memo na kontrolu právnika.",
      nextAction: "Naplánujte 15-minútové hlasové stretnutie s AI agentom na potvrdenie rozsahu.",
      output: "Briefing memo + checklist"
    },
    "case-002": {
      title: "Kontrola zmluvy Atlas",
      description: "Prípad US + Kanada proti Atlas Procurement Vendor.",
      meta: "Čaká sa na dokumenty",
      objective: "Získajte chýbajúce prílohy dodávateľa a zosúlaďte rozsah s procurement tímom.",
      nextAction: "Kontaktujte právnika kvôli chýbajúcemu balíku dokumentov.",
      output: "Redline klauzúl + rizikový súhrn"
    },
    "case-003": {
      title: "Príprava auditu Meridian",
      description: "Prípad EÚ + US proti External Audit Team.",
      meta: "Kickoff dnes",
      objective: "Zosúlaďte auditný checklist a potvrďte harmonogram s internými tímami.",
      nextAction: "Spustite kickoff session a zaznamenajte akčné body.",
      output: "Auditný kickoff deck"
    },
    "case-004": {
      title: "Arbitráž Northwind",
      description: "Prípad UK proti Northwind Counterparty.",
      meta: "Ukončené minulý týždeň",
      objective: "Finalizujte arbitrážny súhrn a archivujte dokumentáciu prípadu.",
      nextAction: "Pošlite záverečné memo výkonným stakeholderom.",
      output: "Balík arbitrážneho súhrnu"
    }
  },
  de: {
    "case-001": {
      title: "Keystone Holdings Intake",
      description: "EU + UK-Fall gegen Northshore Advisory.",
      meta: "Fällig in 2 Tagen",
      objective: "Jurisdiktionsanalyse konsolidieren und ein Briefing-Memo für die Anwaltsprüfung vorbereiten.",
      nextAction: "Planen Sie eine 15-minütige Sprachsitzung mit dem KI-Agenten zur Scope-Bestätigung.",
      output: "Briefing-Memo + Checkliste"
    },
    "case-002": {
      title: "Atlas Vertragsprüfung",
      description: "US + Kanada-Fall gegen Atlas Procurement Vendor.",
      meta: "Wartet auf Dokumente",
      objective: "Fehlende Anbieteranlagen sammeln und den Umfang mit der Beschaffung abstimmen.",
      nextAction: "Mit dem Anwalt zum ausstehenden Dokumentensatz nachfassen.",
      output: "Klausel-Redline + Risikozusammenfassung"
    },
    "case-003": {
      title: "Meridian Auditvorbereitung",
      description: "EU + US-Fall gegen External Audit Team.",
      meta: "Kickoff heute",
      objective: "Audit-Checkliste abstimmen und Zeitplan mit internen Teams bestätigen.",
      nextAction: "Kickoff-Sitzung starten und Aktionspunkte festhalten.",
      output: "Audit-Kickoff-Deck"
    },
    "case-004": {
      title: "Northwind Schiedsverfahren",
      description: "UK-Fall gegen Northwind Counterparty.",
      meta: "Letzte Woche abgeschlossen",
      objective: "Schiedsverfahrenszusammenfassung finalisieren und Falldokumentation archivieren.",
      nextAction: "Abschlussmemo an die Führungsebene senden.",
      output: "Schiedsverfahrenspaket"
    }
  }
};

export const isSeededCaseTemplateId = (value: string): value is SeededCaseTemplateId => {
  return value === "case-001" || value === "case-002" || value === "case-003" || value === "case-004";
};

export const getMockCaseTemplate = (
  language: Language,
  templateId: SeededCaseTemplateId
): MockCaseTemplate => {
  return templates[language][templateId];
};
