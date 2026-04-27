import { useSyncExternalStore } from "react";

/* Tick global cada segundo. Un solo intervalo para toda la app, para que
   reloj/fecha en distintos componentes queden sincronizados sin pisarse. */

let intervalId: ReturnType<typeof setInterval> | null = null;
const subscribers = new Set<() => void>();
let now = new Date();

function startTicking(): void {
  if (intervalId !== null) return;
  intervalId = setInterval(() => {
    now = new Date();
    for (const fn of subscribers) fn();
  }, 1000);
}

function stopTicking(): void {
  if (intervalId !== null) {
    clearInterval(intervalId);
    intervalId = null;
  }
}

function subscribe(fn: () => void): () => void {
  subscribers.add(fn);
  startTicking();
  return () => {
    subscribers.delete(fn);
    if (subscribers.size === 0) stopTicking();
  };
}

function getSnapshot(): Date {
  return now;
}

export function useNow(): Date {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

const ET_TIME = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/New_York",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const ET_DATE = new Intl.DateTimeFormat("es-ES", {
  timeZone: "America/New_York",
  weekday: "short",
  day: "2-digit",
  month: "short",
  year: "numeric",
});

export function formatEtTime(d: Date): string {
  return `${ET_TIME.format(d)} ET`;
}

export function formatEtDate(d: Date): string {
  return ET_DATE.format(d).toLowerCase().replace(/\.,?/g, "");
}
