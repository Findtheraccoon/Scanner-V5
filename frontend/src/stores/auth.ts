import { setBearerToken } from "@/api/client";
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  setToken: (token: string | null) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      setToken: (token) => {
        setBearerToken(token);
        set({ token });
      },
    }),
    {
      name: "scanner-v5-auth",
      onRehydrateStorage: () => (state) => {
        if (state) setBearerToken(state.token);
      },
    },
  ),
);
