import { useAuth } from "../auth/AuthContext";

export function DashboardHomePage() {
  const { user } = useAuth();

  return (
    <div>
      <h1>Welcome{user ? `, ${user.display_name}` : ""}</h1>
      <p>Use the navigation on the left to review tickets or manage your organization's settings.</p>
    </div>
  );
}
