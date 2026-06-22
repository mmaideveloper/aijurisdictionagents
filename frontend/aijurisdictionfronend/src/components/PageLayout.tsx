import React from "react";
import { useLocation } from "react-router-dom";
import { Navigation } from "./Navigation";
import { Footer } from "./Footer";
import { Sidebar } from "./Sidebar";
import { isAgentHost } from "../routing";

export const PageLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { pathname } = useLocation();
  const hasAssistantLayout = (pathname === "/" && isAgentHost()) || pathname === "/app/assistant";

  if (hasAssistantLayout) {
    return (
      <div className="app-shell app-shell--assistant">
        <Navigation isSidebarCollapsed />
        <div className="app-shell__body app-shell__body--assistant">
          <Sidebar />
          <main className="main-content">{children}</main>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Navigation isSidebarCollapsed={false} />
      <main className="main-content">{children}</main>
      <Footer />
    </div>
  );
};
