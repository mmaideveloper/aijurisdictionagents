import React from "react";
import { useLocation } from "react-router-dom";
import { Navigation } from "./Navigation";
import { Footer } from "./Footer";

export const PageLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { pathname } = useLocation();
  const hasAssistantLayout = pathname === "/" || pathname === "/app/assistant";

  if (hasAssistantLayout) {
    return (
      <div className="app-shell app-shell--assistant">
        <main className="main-content">{children}</main>
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
