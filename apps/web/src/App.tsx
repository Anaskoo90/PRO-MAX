import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { LoginPage } from "./auth/LoginPage";
import { AppShell } from "./layout/AppShell";
import { DashboardHomePage } from "./pages/DashboardHomePage";
import { TicketsPage } from "./pages/TicketsPage";
import { MembersPage } from "./pages/MembersPage";
import { MemberDetailPage } from "./pages/MemberDetailPage";
import { RolesPage } from "./pages/RolesPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route index element={<DashboardHomePage />} />
              <Route path="tickets" element={<TicketsPage />} />
              <Route path="members" element={<MembersPage />} />
              <Route path="members/:userId" element={<MemberDetailPage />} />
              <Route path="roles" element={<RolesPage />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
