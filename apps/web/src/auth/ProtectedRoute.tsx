import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

export function ProtectedRoute() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <p>Loading…</p>;
  }
  if (status === "anonymous") {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <Outlet />;
}
