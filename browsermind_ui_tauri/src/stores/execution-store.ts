import { create } from "zustand";

interface ExecutionState {
  selectedExecutionId: string | null;
  setSelectedExecutionId: (id: string | null) => void;
}

export const useExecutionStore = create<ExecutionState>((set) => ({
  selectedExecutionId: null,
  setSelectedExecutionId: (id) => set({ selectedExecutionId: id }),
}));
