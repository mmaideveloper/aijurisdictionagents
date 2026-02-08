import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { PageLayout } from "./components/PageLayout";
import Home from "./pages/Home";
import Auth from "./pages/Auth";
import Pricing from "./pages/Pricing";
import AppDashboard from "./pages/AppDashboard";
import CaseIntake from "./pages/CaseIntake";
import LawyerWorkspace from "./pages/LawyerWorkspace";
import AdviceSummary from "./pages/AdviceSummary";
import Communication from "./pages/Communication";
import LawValidation from "./pages/LawValidation";
import LawRecommendation from "./pages/LawRecommendation";
import Profile from "./pages/Profile";
import NotFound from "./pages/NotFound";

const App: React.FC = () => {
  return (
    <PageLayout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/auth" element={<Auth />} />
        <Route path="/pricing" element={<Pricing />} />
        <Route path="/app" element={<AppDashboard />} />
        <Route path="/app/case" element={<CaseIntake />} />
        <Route path="/app/workspace" element={<LawyerWorkspace />} />
        <Route path="/app/advice" element={<AdviceSummary />} />
        <Route path="/app/communications" element={<Communication />} />
        <Route path="/app/law-validation" element={<LawValidation />} />
        <Route path="/app/law-recommendation" element={<LawRecommendation />} />
        <Route path="/app/profile" element={<Profile />} />
        <Route path="/home" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </PageLayout>
  );
};

export default App;
