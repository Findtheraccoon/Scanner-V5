import { QueryClient } from "@tanstack/react-query";

/* Singleton del QueryClient. Vive en su propio módulo para que código
   fuera de la jerarquía React (WS dispatcher, etc.) pueda invalidar
   queries sin pasar por hooks. */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
