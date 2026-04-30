import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { ToastProvider } from "./components/Toast/ToastProvider";
import { router } from "./router";
import { useAuthStore } from "./stores/auth";
import "./styles/global.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

/* Auto-inject del bearer cuando el backend lo sirve via <meta>.
   Modo launcher (ejecutable único): el backend genera un bearer al
   primer arranque y lo inyecta como `<meta name="scanner-bearer">`
   en el index.html. Si el frontend no tiene token guardado en
   localStorage, lo toma del meta. Modo dev (Vite proxy) el meta no
   existe → el usuario pega el bearer en el footer manualmente. */
function autoInjectBearer(): void {
  try {
    const meta = document.querySelector<HTMLMetaElement>('meta[name="scanner-bearer"]');
    const token = meta?.content?.trim();
    if (!token) return;
    const current = useAuthStore.getState().token;
    if (current) return; // ya hay token guardado; no pisar.
    useAuthStore.getState().setToken(token);
  } catch {
    // Ignorar — sin meta el flujo es manual.
  }
}
autoInjectBearer();

/* En modo launcher, al cerrar la pestaña el WS se desconecta y el
   backend dispara su timer de idle-shutdown (60s). El sendBeacon es
   complementario: notifica al backend con un POST sin auth handshake
   para acelerar el shutdown si querés cerrar el tab inmediatamente.

   IMPORTANTE: el backend ya maneja el caso vía WS counter. Este
   beacon es opcional — si falla (sin token, browser lo ignora, etc.),
   el flujo del WS counter cubre. */
window.addEventListener("beforeunload", () => {
  // No-op por ahora — el WS disconnect alcanza para disparar el
  // grace timer del backend. Si en el futuro queremos shutdown
  // inmediato sin esperar 60s, podríamos hacer:
  //   navigator.sendBeacon("/api/v1/system/shutdown", ...);
  // pero requiere bearer en headers que sendBeacon no soporta.
});

const root = document.getElementById("root");
if (!root) throw new Error("#root no encontrado en index.html");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
