import React from "react";
import { useLocation } from "react-router-dom";
import { Navigation } from "./Navigation";
import { Footer } from "./Footer";
import { useAuth } from "../auth/mockAuth";
import { Sidebar } from "./Sidebar";

export const PageLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  const { pathname } = useLocation();
  const hasWorkspaceLayout = isAuthenticated && pathname === "/";

  if (hasWorkspaceLayout) {
    return (
      <div className="app-shell app-shell--workspace">
        <Sidebar />
        <div className="app-shell__main">
          <Navigation />
          <main className="main-content">{children}</main>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Navigation />
      <main className="main-content">{children}</main>
      <Footer />
    </div>
  );
};
