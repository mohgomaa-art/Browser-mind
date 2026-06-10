import type { AppMode } from "@/stores";

type SharedSection =
  | "home"
  | "work"
  | "accounts"
  | "sessions"
  | "automations"
  | "analytics"
  | "tasks"
  | "executions"
  | "workflows";

const USER_PATHS: Record<SharedSection, string> = {
  home: "/",
  work: "/work",
  accounts: "/accounts",
  sessions: "/sessions",
  automations: "/automations",
  analytics: "/analytics",
  tasks: "/work",
  executions: "/sessions",
  workflows: "/automations",
};

const DEV_PATHS: Record<SharedSection, string> = {
  home: "/dev",
  work: "/dev/tasks",
  accounts: "/dev/identities",
  sessions: "/dev/executions",
  automations: "/dev/workflows",
  analytics: "/dev/analytics",
  tasks: "/dev/tasks",
  executions: "/dev/executions",
  workflows: "/dev/workflows",
};

export function routeFor(section: SharedSection, mode: AppMode): string {
  return mode === "developer" ? DEV_PATHS[section] : USER_PATHS[section];
}

export function taskRoute(id: string, mode: AppMode): string {
  return mode === "developer" ? `/dev/tasks/${id}` : `/work/${id}`;
}

export function executionRoute(id: string, mode: AppMode): string {
  return mode === "developer" ? `/dev/executions/${id}` : `/sessions/${id}`;
}

export function workflowRoute(id: string, mode: AppMode): string {
  return mode === "developer" ? `/dev/workflows/${id}` : `/automations/${id}`;
}

export function environmentRoute(key: string, mode: AppMode): string {
  return mode === "developer" ? `/dev/environments` : `/accounts/${key}`;
}
