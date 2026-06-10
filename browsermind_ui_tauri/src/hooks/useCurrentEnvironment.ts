import { useQuery } from "@tanstack/react-query";
import { adapter } from "@/lib/adapters";
import { queryKeys } from "@/lib/queries";
import { useEnvironmentStore } from "@/stores/environment-store";
import type { Environment } from "@/types";

/**
 * Returns the currently-selected Environment based on the environment store,
 * or null if none is selected (or while loading).
 */
export function useCurrentEnvironment(): {
  environment: Environment | null;
  isLoading: boolean;
} {
  const currentEnvironmentKey = useEnvironmentStore(
    (s) => s.currentEnvironmentKey,
  );
  const query = useQuery({
    queryKey: queryKeys.environment(currentEnvironmentKey ?? ""),
    queryFn: () => adapter.environments.byKey(currentEnvironmentKey as string),
    enabled: !!currentEnvironmentKey,
  });
  return {
    environment: query.data ?? null,
    isLoading: query.isLoading,
  };
}
