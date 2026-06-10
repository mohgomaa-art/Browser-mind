import { create } from "zustand";

interface TaskState {
  selectedTaskId: string | null;
  setSelectedTaskId: (id: string | null) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  selectedTaskId: null,
  setSelectedTaskId: (id) => set({ selectedTaskId: id }),
}));
