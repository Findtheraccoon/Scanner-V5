import { Pilot } from "@/components/ui/Pilot";
import type { ReactElement } from "react";
import { Box } from "./Box";
import { Frame } from "./Frame";
import "./configuration.css";

/* ConfigurationPage · root de la pestaña Configuración.

   Layout:
   - Header con título + indicador overall.
   - Frame con 6 boxes plegables (subgrid · dot por box).

   El contenido real de cada box vive en `boxes/Box*.tsx` y se cablea
   con su propio hook de TanStack Query / store. En este commit 3 los
   boxes están con placeholders mínimos — se rellenan en commits 4–9. */

export function ConfigurationPage(): ReactElement {
  return (
    <main className="cfg-page">
      <header className="cfg-page__header">
        <div>
          <h1 className="cfg-page__title">
            Configuración del Scanner <em>v5.2.0</em>
          </h1>
          <div className="cfg-page__sub">
            6 pasos verticales · cada paso es independiente · auto-collapse al quedar OK
          </div>
        </div>
        <div className="cfg-page__overall">
          <span className="lab">overall</span>
          <span className="ratio">— en preparación —</span>
          <Pilot state="pend" />
        </div>
      </header>

      <Frame>
        <Box
          id={1}
          state="pend"
          title="Motores del backend"
          sub="5 motores arrancan con el lifespan FastAPI · esta vista es sólo observabilidad"
          statusText="—"
        >
          <div className="note">Pendiente · contenido en commit 4.</div>
        </Box>

        <Box
          id={2}
          state="pend"
          title="Archivo de configuración"
          sub="cargar · guardar · descargar · contiene TD keys + fixtures + preferencias"
          statusText="—"
        >
          <div className="note">Pendiente · contenido en commit 5.</div>
        </Box>

        <Box
          id={3}
          state="pend"
          title="Proveedor de datos · TwelveData"
          sub="5 keys round-robin · KeyPool · probe individual + agregado"
          statusText="—"
        >
          <div className="note">Pendiente · contenido en commit 6.</div>
        </Box>

        <Box
          id={4}
          state="pend"
          title="Slot Registry + fixtures"
          sub="6 slots fijos · enable/disable dispara warmup + revalidación A/B/C"
          statusText="—"
        >
          <div className="note">Pendiente · contenido en commit 7.</div>
        </Box>

        <Box
          id={5}
          state="pend"
          title="Validator + diagnóstico"
          sub="batería D / A / B / C / E / F / G · histórico de reportes"
          statusText="—"
        >
          <div className="note">Pendiente · contenido en commit 8.</div>
        </Box>

        <Box
          id={6}
          state="pend"
          title="Backup remoto · S3-compatible"
          sub="AWS · B2 · R2 · MinIO · respaldo offsite"
          statusText="—"
        >
          <div className="note">Pendiente · contenido en commit 9.</div>
        </Box>
      </Frame>
    </main>
  );
}
