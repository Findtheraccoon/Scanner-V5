import type { ReactElement } from "react";

interface ToggleProps {
  on: boolean;
  onChange?: (on: boolean) => void;
  label?: string;
  disabled?: boolean;
  ariaLabel?: string;
}

/* Toggle on/off compacto (clase global `.toggle`). El label muestra
   "ON" / "OFF" por default; pasar `label` lo overrides.
   `onChange` se invoca con el nuevo valor (negado del actual). */
export function Toggle({
  on,
  onChange,
  label,
  disabled = false,
  ariaLabel,
}: ToggleProps): ReactElement {
  const cls = on ? "toggle is-on" : "toggle";
  const text = label ?? (on ? "on" : "off");
  return (
    <button
      type="button"
      className={cls}
      onClick={() => !disabled && onChange?.(!on)}
      disabled={disabled}
      aria-pressed={on}
      aria-label={ariaLabel}
    >
      <span className="toggle__sw" />
      <span className="toggle__lbl">{text}</span>
    </button>
  );
}
