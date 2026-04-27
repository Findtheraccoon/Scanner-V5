import { Navigate, createBrowserRouter } from "react-router-dom";
import { AppShell } from "./components/AppShell/AppShell";
import { CockpitPage } from "./pages/Cockpit/CockpitPage";
import { ConfigurationPage } from "./pages/Configuration/ConfigurationPage";
import { DashboardPage } from "./pages/Dashboard/DashboardPage";
import { MementoPage } from "./pages/Memento/MementoPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/cockpit" replace /> },
      { path: "configuracion", element: <ConfigurationPage /> },
      { path: "dashboard", element: <DashboardPage /> },
      { path: "cockpit", element: <CockpitPage /> },
      { path: "memento", element: <MementoPage /> },
    ],
  },
]);
