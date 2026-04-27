import { NavLink, Outlet } from "react-router-dom";
import { ApiBar } from "./ApiBar";
import { Footer } from "./Footer";
import { TopBar } from "./TopBar";
import "@/styles/shell.css";

const TABS = [
  { to: "/configuracion", label: "configuración" },
  { to: "/dashboard", label: "dashboard" },
  { to: "/cockpit", label: "cockpit" },
  { to: "/memento", label: "memento" },
] as const;

export function AppShell() {
  return (
    <>
      <div className="health-line" />
      <div className="app">
        <TopBar>
          <nav className="topbar__nav" aria-label="pestañas">
            {TABS.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) => (isActive ? "tab is-active" : "tab")}
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </TopBar>
        <ApiBar />
        <Outlet />
        <Footer />
      </div>
    </>
  );
}
