import { create } from "zustand";

export type InspectorEntityType =
  | "task"
  | "execution"
  | "identity"
  | "environment"
  | "workflow"
  | "persona"
  | null;

export interface InspectorSelection {
  type: InspectorEntityType;
  id: string | null;
}

interface InspectorState {
  selected: InspectorSelection;
  open: boolean;
  setSelected: (selection: InspectorSelection) => void;
  setOpen: (open: boolean) => void;
  toggle: () => void;
}

export const useInspectorStore = create<InspectorState>((set, get) => ({
  selected: { type: null, id: null },
  open: false,
  setSelected: (selection) => set({ selected: selection }),
  setOpen: (open) => set({ open }),
  toggle: () => set({ open: !get().open }),
}));
