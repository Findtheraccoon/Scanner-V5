import { useEngineHealth, useSlots } from "@/api/queries";
import { useScannerWS } from "@/api/ws";
import { useApiUsageStore } from "@/stores/apiUsage";
import { useEngineStore } from "@/stores/engine";
import { useSlotsStore } from "@/stores/slots";
import { useEffect } from "react";
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

/* Wire de stores con datos del backend. Se monta una sola vez al cargar
   el shell. El WS dispatchea engine.status/slot.status/api_usage.tick a
   sus stores; el seed inicial viene de useSlots() y useEngineHealth(). */
function useBackendWiring(): void {
  useScannerWS();
  const slotsQuery = useSlots();
  const healthQuery = useEngineHealth();
  const setSlots = useSlotsStore((s) => s.setSlots);
  const setKeys = useApiUsageStore((s) => s.setKeys);
  const applyEngine = useEngineStore((s) => s.applyEngineStatus);

  useEffect(() => {
    if (slotsQuery.data) setSlots(slotsQuery.data);
  }, [slotsQuery.data, setSlots]);

  useEffect(() => {
    if (!healthQuery.data) return;
    const h = healthQuery.data;
    applyEngine({ engine: "data", status: h.data.status, message: h.data.message });
    applyEngine({ engine: "scoring", status: h.scoring.status, message: h.scoring.message });
    applyEngine({
      engine: "database",
      status: h.database.status,
      message: h.database.message,
    });
  }, [healthQuery.data, applyEngine]);

  useEffect(() => {
    // El endpoint /engine/health no expone keys; las alimentamos por el
    // primer api_usage.tick que llega del WS. Nada que hacer acá por ahora.
    void setKeys;
  }, [setKeys]);
}

export function AppShell() {
  useBackendWiring();
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
