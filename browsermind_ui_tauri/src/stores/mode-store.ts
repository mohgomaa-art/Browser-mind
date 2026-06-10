import { create } from "zustand";
import { persist } from "zustand/middleware";

export type AppMode = "user" | "developer";

interface ModeState {
  mode: AppMode;
  toggle: () => void;
  setMode: (m: AppMode) => void;
}

export const useModeStore = create<ModeState>()(
  persist(
    (set, get) => ({
      mode: "user",
      toggle: () =>
        set({ mode: get().mode === "user" ? "developer" : "user" }),
      setMode: (m) => set({ mode: m }),
    }),
    { name: "bm.mode" },
  ),
);
