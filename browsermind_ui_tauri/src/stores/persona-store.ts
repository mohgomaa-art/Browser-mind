import { create } from "zustand";
import { persist } from "zustand/middleware";

interface PersonaState {
  currentPersonaId: string | null;
  setCurrentPersonaId: (id: string | null) => void;
}

export const usePersonaStore = create<PersonaState>()(
  persist(
    (set) => ({
      currentPersonaId: null,
      setCurrentPersonaId: (id) => set({ currentPersonaId: id }),
    }),
    { name: "bm.persona" },
  ),
);
