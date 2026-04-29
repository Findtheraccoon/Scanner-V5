import { Pilot } from "@/components/ui/Pilot";
import type { ReactElement } from "react";
import { Frame } from "./Frame";
import { Box1Engines } from "./boxes/Box1Engines";
import { Box2Config } from "./boxes/Box2Config";
import { Box3Keys } from "./boxes/Box3Keys";
import { Box4Slots } from "./boxes/Box4Slots";
import { Box5Validator } from "./boxes/Box5Validator";
import { Box6S3 } from "./boxes/Box6S3";
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
        <Box1Engines />
        <Box2Config />
        <Box3Keys />
        <Box4Slots />
        <Box5Validator />
        <Box6S3 />
      </Frame>
    </main>
  );
}
