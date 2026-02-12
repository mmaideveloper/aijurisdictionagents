import React from "react";
import { useLocation } from "react-router-dom";
import { Navigation } from "./Navigation";
import { Footer } from "./Footer";
import { useAuth } from "../auth/mockAuth";
import { Sidebar } from "./Sidebar";
import { BsBoxArrowRight } from "react-icons/bs";

export const PageLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  const { pathname } = useLocation();
  const hasWorkspaceLayout = isAuthenticated && pathname === "/";
  const [sidebarOpen, setSidebarOpen] = React.useState(true);
  const toggleSidebar = () => {
    setSidebarOpen((prev) => !prev);
  };

  if (hasWorkspaceLayout) {
    return (
      <div className="app-shell app-shell--workspace">
        {sidebarOpen ? <Sidebar onClose={toggleSidebar} /> : null}
        {!sidebarOpen ? (
          <button
            type="button"
            className="sidebar-bubble"
            onClick={toggleSidebar}
            aria-label="Open sidebar"
          >
            <BsBoxArrowRight className="sidebar-icon" />
          </button>
        ) : null}
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
