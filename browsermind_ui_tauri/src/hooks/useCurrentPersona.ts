import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import { queryKeys } from "@/lib/queries";
import { usePersonaStore } from "@/stores/persona-store";
import type { Persona } from "@/types";

/**
 * Returns the currently-selected Persona based on the persona store,
 * or null if none is selected (or while loading).
 */
export function useCurrentPersona(): {
  persona: Persona | null;
  isLoading: boolean;
} {
  const currentPersonaId = usePersonaStore((s) => s.currentPersonaId);
  const query = useQuery({
    queryKey: queryKeys.persona(currentPersonaId ?? ""),
    queryFn: () => adapter.personas.byId(currentPersonaId as string),
    enabled: !!currentPersonaId,
  });
  return {
    persona: query.data ?? null,
    isLoading: query.isLoading,
  };
}
