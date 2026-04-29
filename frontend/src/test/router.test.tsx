import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppShell } from "../components/AppShell/AppShell";
import { ToastProvider } from "../components/Toast/ToastProvider";
import { CockpitPage } from "../pages/Cockpit/CockpitPage";
import { ConfigurationPage } from "../pages/Configuration/ConfigurationPage";
import { DashboardPage } from "../pages/Dashboard/DashboardPage";
import { MementoPage } from "../pages/Memento/MementoPage";

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/" element={<AppShell />}>
              <Route path="configuracion" element={<ConfigurationPage />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="cockpit" element={<CockpitPage />} />
              <Route path="memento" element={<MementoPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("AppShell", () => {
  it("renderiza el brand y las 4 pestañas", () => {
    renderAt("/cockpit");
    expect(screen.getByText("scanner")).toBeInTheDocument();
    const nav = screen.getByLabelText("pestañas");
    expect(within(nav).getByText("configuración")).toBeInTheDocument();
    expect(within(nav).getByText("dashboard")).toBeInTheDocument();
    expect(within(nav).getByText("cockpit")).toBeInTheDocument();
    expect(within(nav).getByText("memento")).toBeInTheDocument();
  });

  it("marca la pestaña activa con is-active", () => {
    renderAt("/dashboard");
    const nav = screen.getByLabelText("pestañas");
    expect(within(nav).getByText("dashboard").className).toContain("is-active");
    expect(within(nav).getByText("cockpit").className).not.toContain("is-active");
  });

  it("monta la apibar con las 5 keys (cabezal + diaria)", () => {
    renderAt("/cockpit");
    const apibar = screen.getByLabelText("estado api");
    // cada nombre de key aparece dos veces: en el cabezal de la celda y en
    // la fila de la pila de uso diario.
    expect(within(apibar).getAllByText("key 1")).toHaveLength(2);
    expect(within(apibar).getAllByText("key 5")).toHaveLength(2);
    expect(within(apibar).getByRole("button", { name: /ejecutar scan/i })).toBeInTheDocument();
  });
});

describe("CockpitPage", () => {
  it("renderiza la watchlist con ticker QQQ y el panel con banner del ticker", () => {
    renderAt("/cockpit");
    const watchlist = screen.getByLabelText("watchlist");
    expect(within(watchlist).getByText("QQQ")).toBeInTheDocument();

    const panel = screen.getByLabelText("detalle");
    expect(within(panel).getByRole("heading", { level: 1, name: "QQQ" })).toBeInTheDocument();
    expect(within(panel).getByText("setup")).toBeInTheDocument();
  });
});

describe("Stub pages", () => {
  it("Memento renderiza el stub", () => {
    renderAt("/memento");
    expect(screen.getByRole("heading", { name: "memento" })).toBeInTheDocument();
  });
});

describe("ConfigurationPage", () => {
  it("renderiza el header + los 6 boxes con sus dots", () => {
    renderAt("/configuracion");
    // Título
    expect(screen.getByRole("heading", { name: /configuración del scanner/i })).toBeInTheDocument();
    // 6 boxes — los dots tienen role="button" con aria-label "Expandir/Colapsar sección N: ..."
    for (const i of [1, 2, 3, 4, 5, 6]) {
      expect(screen.getByLabelText(new RegExp(`sección ${i}:`, "i"))).toBeInTheDocument();
    }
  });

  it("los 6 boxes arrancan colapsados por default", () => {
    renderAt("/configuracion");
    // Cada box tiene un aria-label que dice "Expandir" cuando está colapsado.
    // Si fuera al revés (expandido), diría "Colapsar".
    for (const i of [1, 2, 3, 4, 5, 6]) {
      const dot = screen.getByLabelText(new RegExp(`expandir sección ${i}:`, "i"));
      expect(dot).toBeInTheDocument();
    }
  });
});
