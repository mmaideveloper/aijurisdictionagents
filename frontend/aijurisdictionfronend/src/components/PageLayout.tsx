import React from "react";
import { useLocation } from "react-router-dom";
import { Navigation } from "./Navigation";
import { Footer } from "./Footer";
import { useAuth } from "../auth/mockAuth";
import { Sidebar } from "./Sidebar";

const BookClosedIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path
      d="M4 5.5C4 4.12 5.12 3 6.5 3H20v16.5c0 1.1-.9 2-2 2H6.5C5.12 21.5 4 20.38 4 19V5.5z"
      fill="currentColor"
      opacity="0.2"
    />
    <path
      d="M6.5 3H20v16.5c0 1.1-.9 2-2 2H6.5C5.12 21.5 4 20.38 4 19V5.5C4 4.12 5.12 3 6.5 3zm0 1.5C5.95 4.5 5.5 4.95 5.5 5.5V19c0 .55.45 1 1 1H18c.28 0 .5-.22.5-.5V4.5H6.5z"
      fill="currentColor"
    />
  </svg>
);

export const PageLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  const { pathname } = useLocation();
  const hasWorkspaceLayout = isAuthenticated && pathname === "/";
  const [sidebarOpen, setSidebarOpen] = React.useState(true);

  if (hasWorkspaceLayout) {
    return (
      <div
        className={`app-shell app-shell--workspace${sidebarOpen ? "" : " app-shell--sidebar-collapsed"}`}
      >
        {sidebarOpen ? <Sidebar onClose={() => setSidebarOpen(false)} /> : null}
        {!sidebarOpen ? (
          <button
            type="button"
            className="sidebar-bubble sidebar-bubble--open"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open sidebar"
          >
            <BookClosedIcon />
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

