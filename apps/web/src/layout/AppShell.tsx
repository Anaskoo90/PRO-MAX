import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import styles from "./AppShell.module.css";

const NAV_ITEMS: { to: string; label: string; end?: boolean }[] = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/tickets", label: "Tickets" },
  { to: "/members", label: "Members" },
  { to: "/roles", label: "Roles" },
  { to: "/invitations", label: "Invitations" },
  { to: "/settings", label: "Settings" },
];

export function AppShell() {
  const { user, logout } = useAuth();

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>GuildDesk</div>
        <nav className={styles.nav}>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? `${styles.navLink} ${styles.navLinkActive}` : styles.navLink)}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className={styles.main}>
        <header className={styles.topbar}>
          <span className={styles.userEmail}>{user?.email}</span>
          <button className={styles.logoutButton} onClick={() => void logout()}>
            Sign out
          </button>
        </header>
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
