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
  { to: "/cockpit", label: "cockpit" },
  { to: "/dashboard", label: "dashboard" },
  { to: "/memento", label: "memento" },
  { to: "/configuracion", label: "configuración" },
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
    // El endpoint /engine/health solo expone scoring (lee del heartbeat).
    // Los otros motores (data, database, validator) llegan por WS
    // engine.status — el store los mantiene en "offline" hasta que
    // reporten. Cuando el backend amplíe el endpoint a multi-motor,
    // este wiring se extiende.
    applyEngine({
      engine: "scoring",
      status: h.status,
      error_code: h.error_code ?? undefined,
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
