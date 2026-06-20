import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { PageLayout } from "./components/PageLayout";
import { useAuth } from "./auth/webAuth";
import AuthCallbackView from "./auth/AuthCallbackView";
import Home from "./pages/Home";
import Auth from "./pages/Auth";
import Pricing from "./pages/Pricing";
import AppDashboard from "./pages/AppDashboard";
import AssistantWorkspace from "./pages/AssistantWorkspace";
import CaseIntake from "./pages/CaseIntake";
import LawyerWorkspace from "./pages/LawyerWorkspace";
import AdviceSummary from "./pages/AdviceSummary";
import Communication from "./pages/Communication";
import LawValidation from "./pages/LawValidation";
import LawRecommendation from "./pages/LawRecommendation";
import Profile from "./pages/Profile";
import Disclaimer from "./pages/Disclaimer";
import PrivacyPolicy from "./pages/PrivacyPolicy";
import TermsOfService from "./pages/TermsOfService";
import NotFound from "./pages/NotFound";

interface ProtectedRouteProps {
  children: React.ReactElement;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return children;
};

const App: React.FC = () => {
  return (
    <PageLayout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/auth" element={<Auth />} />
        <Route
          path="/auth/callback"
          element={<AuthCallbackView onSessionReady={() => undefined} />}
        />
        <Route path="/pricing" element={<Pricing />} />
        <Route
          path="/app"
          element={
            <ProtectedRoute>
              <AppDashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/assistant"
          element={
            <ProtectedRoute>
              <AssistantWorkspace />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/case"
          element={
            <ProtectedRoute>
              <CaseIntake />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/workspace"
          element={
            <ProtectedRoute>
              <LawyerWorkspace />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/advice"
          element={
            <ProtectedRoute>
              <AdviceSummary />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/communications"
          element={
            <ProtectedRoute>
              <Communication />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/law-validation"
          element={
            <ProtectedRoute>
              <LawValidation />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/law-recommendation"
          element={
            <ProtectedRoute>
              <LawRecommendation />
            </ProtectedRoute>
          }
        />
        <Route
          path="/app/profile"
          element={<Navigate to="/profile" replace />}
        />
        <Route
          path="/profile"
          element={
            <ProtectedRoute>
              <Profile />
            </ProtectedRoute>
          }
        />
        <Route path="/privacy" element={<PrivacyPolicy />} />
        <Route path="/disclaimer" element={<Disclaimer />} />
        <Route path="/terms" element={<TermsOfService />} />
        <Route path="/home" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </PageLayout>
  );
};

export default App;
