import { create } from "zustand";
import { persist } from "zustand/middleware";

interface EnvironmentState {
  currentEnvironmentKey: string | null;
  setCurrentEnvironmentKey: (key: string | null) => void;
}

export const useEnvironmentStore = create<EnvironmentState>()(
  persist(
    (set) => ({
      currentEnvironmentKey: null,
      setCurrentEnvironmentKey: (key) => set({ currentEnvironmentKey: key }),
    }),
    { name: "bm.env" },
  ),
);
