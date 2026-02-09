import React from "react";
import { Navigation } from "./Navigation";
import { Footer } from "./Footer";

export const PageLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="app-shell">
      <Navigation />
      <main className="main-content">{children}</main>
      <Footer />
    </div>
  );
};
