import type { ReactElement, ReactNode } from "react";

interface FrameProps {
  children: ReactNode;
}

/* Contenedor visual de los 6 boxes. Implementa el grid 2-col con
   subgrid donde la columna 1 es el rail (dot del box) y la columna
   2 el contenido. La línea vertical del rail es un `::before` del
   propio frame definido en `configuration.css`. */
export function Frame({ children }: FrameProps): ReactElement {
  return <section className="cfg-frame">{children}</section>;
}
