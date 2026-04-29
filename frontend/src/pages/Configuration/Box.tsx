import { Pilot } from "@/components/ui/Pilot";
import type { BoxId } from "@/stores/configUi";
import { useConfigUiStore } from "@/stores/configUi";
import type { ReactElement, ReactNode } from "react";

export type BoxState = "ok" | "warn" | "err" | "pend";

interface BoxProps {
  id: BoxId;
  state: BoxState;
  title: string;
  /* Subtítulo que vive bajo el título — admite ReactNode para poder
     incluir `<span class="ref">…</span>` con palabras de acento. */
  sub: ReactNode;
  /* Texto del badge de estado en el head — sin pilot ni pill, solo
     el contenido. La pill + pilot se aplican automáticamente con
     `state`. */
  statusText: ReactNode;
  children: ReactNode;
}

/* Box plegable de la pestaña Configuración. Con subgrid: dot vive en
   col 1 alineado al box-head; head + body en col 2 (rows 1 y 2). El
   collapse state se guarda en `useConfigUiStore`. */
export function Box({ id, state, title, sub, statusText, children }: BoxProps): ReactElement {
  const collapsed = useConfigUiStore((s) => s.collapsed[id]);
  const toggle = useConfigUiStore((s) => s.toggle);

  const onHeadClick = (e: React.MouseEvent<HTMLElement>) => {
    // Ignora clicks en controles internos del head (el statusText puede
    // llevar pills/iconos clickeables en algún caso futuro).
    const target = e.target as HTMLElement;
    if (target.closest("button, input, .toggle, .fix-select, .fix-dropdown")) return;
    toggle(id);
  };

  const cls = `cfg-box is-${state}${collapsed ? " is-collapsed" : ""}`;
  const pilotState = state === "ok" ? "ok" : state;

  return (
    <article className={cls} id={`box-${id}`} data-box={id}>
      <button
        type="button"
        className="cfg-box__dot"
        onClick={() => toggle(id)}
        aria-label={`${collapsed ? "Expandir" : "Colapsar"} sección ${id}: ${title}`}
      >
        {id}
      </button>
      <header
        className="cfg-box__head"
        // biome-ignore lint/a11y/useKeyWithClickEvents: el header delega en el button del dot para activación con teclado; clic en el header es UX adicional.
        // biome-ignore lint/a11y/useSemanticElements: el header lleva onClick como afordancia visual; el button del dot es el control real.
        onClick={onHeadClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggle(id);
          }
        }}
        aria-expanded={!collapsed}
      >
        <div className="cfg-box__title-wrap">
          <div className="cfg-box__title">{title}</div>
          <div className="cfg-box__sub">{sub}</div>
        </div>
        <div className="cfg-box__meta">
          <span className="cfg-box__status">
            <Pilot state={pilotState} />
            {statusText}
          </span>
          <span className="cfg-box__chev" aria-hidden="true">
            ▾
          </span>
        </div>
      </header>
      <div className="cfg-box__body">{children}</div>
    </article>
  );
}
