import type { ReactElement, ReactNode } from "react";

export type BadgeVariant = "default" | "ok" | "warn" | "err" | "run" | "pend";

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}

/* Badge pill con variantes de color (clases globales `.badge`,
   `.badge.is-*` definidas en `configuration.css`). */
export function Badge({ variant = "default", children, className }: BadgeProps): ReactElement {
  const base = variant === "default" ? "badge" : `badge is-${variant}`;
  return <span className={className ? `${base} ${className}` : base}>{children}</span>;
}
