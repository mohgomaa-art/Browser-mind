import { useQuery } from "@tanstack/react-query";
import { adapter } from "./adapters";
import type {
  ExecutionState,
  MemoryType,
  TaskState,
} from "@/types";

export const queryKeys = {
  principals: ["principals"] as const,
  personas: ["personas"] as const,
  persona: (id: string) => ["persona", id] as const,
  identities: (personaId?: string) => ["identities", personaId ?? null] as const,
  environments: ["environments"] as const,
  environment: (key: string) => ["environment", key] as const,
  tasks: (filter?: { state?: TaskState; personaId?: string }) =>
    ["tasks", filter ?? {}] as const,
  task: (id: string) => ["task", id] as const,
  executions: (filter?: { taskId?: string; state?: ExecutionState }) =>
    ["executions", filter ?? {}] as const,
  execution: (id: string) => ["execution", id] as const,
  workflows: ["workflows"] as const,
  workflow: (id: string) => ["workflow", id] as const,
  replays: (filter?: object) => ["replays", filter ?? {}] as const,
  replay: (id: string) => ["replay", id] as const,
  ledger: (filter?: object) => ["ledger", filter ?? {}] as const,
  memory: (type?: MemoryType) => ["memory", type ?? null] as const,
  analytics: ["analytics"] as const,
  systemStatus: ["system-status"] as const,
};

// ─── Convenience hooks ───────────────────────────────────────────────────────

export function useTasks(filter?: { state?: TaskState; personaId?: string }) {
  return useQuery({
    queryKey: queryKeys.tasks(filter),
    queryFn: () => adapter.tasks.list(filter),
  });
}

export function useTask(id: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.task(id ?? ""),
    queryFn: () => adapter.tasks.byId(id as string),
    enabled: !!id,
  });
}

export function useExecutions(filter?: {
  taskId?: string;
  state?: ExecutionState;
}) {
  return useQuery({
    queryKey: queryKeys.executions(filter),
    queryFn: () => adapter.executions.list(filter),
    refetchInterval: (query) => {
      const data = query.state.data ?? [];
      const hasLive = data.some(
        (e) => e.state === "running" || e.state === "paused" || e.state === "waiting",
      );
      return hasLive ? 3000 : false;
    },
  });
}

export function useExecution(id: string | null | undefined) {
  return useQuery({
    queryKey: queryKeys.execution(id ?? ""),
    queryFn: () => adapter.executions.byId(id as string),
    enabled: !!id,
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state === "running" || state === "paused" || state === "waiting"
        ? 2000
        : false;
    },
  });
}

export function useReplays(filter?: {
  workflowId?: string;
  environmentKey?: string;
}) {
  return useQuery({
    queryKey: queryKeys.replays(filter),
    queryFn: () => adapter.replays.list(filter),
  });
}

export function useEnvironments() {
  return useQuery({
    queryKey: queryKeys.environments,
    queryFn: () => adapter.environments.list(),
  });
}

export function useIdentities(personaId?: string) {
  return useQuery({
    queryKey: queryKeys.identities(personaId),
    queryFn: () => adapter.identities.list(personaId),
  });
}

export function useAnalytics() {
  return useQuery({
    queryKey: queryKeys.analytics,
    queryFn: () => adapter.analytics.metrics(),
  });
}

export function useSystemStatus() {
  return useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: () => adapter.system.status(),
    refetchInterval: 5000,
  });
}
