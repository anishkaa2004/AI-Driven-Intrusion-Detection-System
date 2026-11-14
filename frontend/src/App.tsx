import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./app/auth";
import { LiveProvider } from "./app/live";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import AlertDetailPage from "./pages/AlertDetail";
import AlertsPage from "./pages/Alerts";
import AnalyticsPage from "./pages/Analytics";
import AuditPage from "./pages/Audit";
import DashboardPage from "./pages/Dashboard";
import DevicesPage from "./pages/Devices";
import LivePage from "./pages/Live";
import LoginPage from "./pages/Login";
import SettingsPage from "./pages/Settings";

function Protected() {
  const { user, loading } = useAuth();
  if (loading) {
    return <div className="flex h-screen items-center justify-center"><Spinner /></div>;
  }
  if (!user) return <Navigate to="/login" replace />;
  return (
    <LiveProvider>
      <Layout />
    </LiveProvider>
  );
}

function LoginRoute() {
  const { user } = useAuth();
  return user ? <Navigate to="/" replace /> : <LoginPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route element={<Protected />}>
            <Route index element={<DashboardPage />} />
            <Route path="live" element={<LivePage />} />
            <Route path="threats" element={<AlertsPage mode="threats" />} />
            <Route path="history" element={<AlertsPage mode="history" />} />
            <Route path="alerts/:id" element={<AlertDetailPage />} />
            <Route path="devices" element={<DevicesPage />} />
            <Route path="analytics" element={<AnalyticsPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="audit" element={<AuditPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
