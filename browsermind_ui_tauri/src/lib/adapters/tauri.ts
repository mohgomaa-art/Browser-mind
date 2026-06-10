import type {
  AnalyticsMetrics,
  Environment,
  Execution,
  ExecutionState,
  Identity,
  LedgerEvent,
  LedgerKind,
  MemoryEntry,
  MemoryType,
  MissionCounts,
  MissionEntry,
  MissionLiveState,
  Persona,
  Principal,
  ReplayReport,
  Task,
  TaskState,
  WorkflowTemplate,
} from "@/types";
import type { SystemStatus } from "./mock";

export const SIDECAR_BASE = "http://127.0.0.1:8766";
const BASE = SIDECAR_BASE;

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`sidecar error: ${r.status} ${path}`);
  return r.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`sidecar error: ${r.status} ${path}`);
  return r.json();
}

export interface TrainingStatus {
  episodeCount: number;
  checkpointLoaded: boolean;
  checkpointPath: string;
  actionAcc: number;
  valLoss: number;
  lastTrainedAt: string;
}

export interface RecoveryCandidate {
  id: string;
  [key: string]: unknown;
}

export interface BenchmarkReport {
  filename: string;
  timestamp: string;
  aggregateSuccessRate: number;
  workflowCount: number;
  runsPerWorkflow: number;
  workflows: { name: string; successRate: number; description: string }[];
}

export interface ExploreRun {
  runId: string;
  siteKey: string;
  budget: number;
  status: "running" | "complete" | "error";
  stepsExecuted: number;
  experiencesDiscovered: string[];
  hypothesisCount: number;
  durationSeconds: number;
  error: string | null;
  startedAt: string;
}

export interface FallbackLedgerStats {
  uniqueFragments: number;
  totalObservations: number;
  multiSiteFragments: number;
  topFragments: { fragment: string; freq: number; sites: number }[];
}

export interface VocabProposalSummary {
  total: number;
  byStatus: Record<string, number>;
}

export const tauriAdapter = {
  principals: {
    async list(): Promise<Principal[]> {
      return get("/api/principals");
    },
  },
  personas: {
    async list(): Promise<Persona[]> {
      return get("/api/personas");
    },
    async byId(id: string): Promise<Persona | null> {
      return get(`/api/personas/${id}`);
    },
  },
  identities: {
    async list(personaId?: string): Promise<Identity[]> {
      const qs = personaId ? `?personaId=${personaId}` : "";
      return get(`/api/identities${qs}`);
    },
    async byId(id: string): Promise<Identity | null> {
      return get(`/api/identities/${id}`);
    },
  },
  environments: {
    async list(): Promise<Environment[]> {
      return get("/api/environments");
    },
    async byKey(key: string): Promise<Environment | null> {
      return get(`/api/environments/${key}`);
    },
  },
  tasks: {
    async list(filter?: { state?: TaskState; personaId?: string }): Promise<Task[]> {
      const params = new URLSearchParams();
      if (filter?.state) params.set("state", filter.state);
      if (filter?.personaId) params.set("personaId", filter.personaId);
      const qs = params.toString() ? `?${params}` : "";
      return get(`/api/tasks${qs}`);
    },
    async byId(id: string): Promise<Task | null> {
      return get(`/api/tasks/${id}`);
    },
  },
  executions: {
    async list(filter?: { taskId?: string; state?: ExecutionState }): Promise<Execution[]> {
      const params = new URLSearchParams();
      if (filter?.taskId) params.set("taskId", filter.taskId);
      if (filter?.state) params.set("state", filter.state);
      const qs = params.toString() ? `?${params}` : "";
      return get(`/api/executions${qs}`);
    },
    async byId(id: string): Promise<Execution | null> {
      return get(`/api/executions/${id}`);
    },
    async act(id: string, action: "pause" | "resume" | "retry" | "cancel"): Promise<void> {
      return post(`/api/executions/${id}/act`, { action });
    },
  },
  workflows: {
    async list(): Promise<WorkflowTemplate[]> {
      return get("/api/workflows");
    },
    async byId(id: string): Promise<WorkflowTemplate | null> {
      return get(`/api/workflows/${id}`);
    },
  },
  replays: {
    async list(filter?: {
      workflowId?: string;
      environmentKey?: string;
    }): Promise<ReplayReport[]> {
      const params = new URLSearchParams();
      if (filter?.workflowId) params.set("workflowId", filter.workflowId);
      if (filter?.environmentKey) params.set("environmentKey", filter.environmentKey);
      const qs = params.toString() ? `?${params}` : "";
      return get(`/api/replays${qs}`);
    },
    async byId(id: string): Promise<ReplayReport | null> {
      return get(`/api/replays/${id}`);
    },
  },
  ledger: {
    async list(filter?: {
      kind?: LedgerKind;
      since?: string;
      entityType?: string;
    }): Promise<LedgerEvent[]> {
      const params = new URLSearchParams();
      if (filter?.kind) params.set("kind", filter.kind);
      if (filter?.since) params.set("since", filter.since);
      if (filter?.entityType) params.set("entityType", filter.entityType);
      const qs = params.toString() ? `?${params}` : "";
      return get(`/api/ledger${qs}`);
    },
  },
  memory: {
    async list(type?: MemoryType): Promise<MemoryEntry[]> {
      const qs = type ? `?type=${type}` : "";
      return get(`/api/memory${qs}`);
    },
  },
  analytics: {
    async metrics(): Promise<AnalyticsMetrics> {
      return get("/api/analytics/metrics");
    },
  },
  system: {
    async status(): Promise<SystemStatus> {
      return get("/api/system/status");
    },
  },
  training: {
    async status(): Promise<TrainingStatus> {
      return get("/api/training/status");
    },
    async startTrain(): Promise<{ started: boolean }> {
      return post("/api/training/train");
    },
    async startSelfTrain(): Promise<{ started: boolean }> {
      return post("/api/training/self-train");
    },
  },
  recovery: {
    async listCandidates(): Promise<RecoveryCandidate[]> {
      return get("/api/recovery/candidates");
    },
    async approve(id: string): Promise<{ ok: boolean }> {
      return post(`/api/recovery/candidates/${id}/approve`);
    },
    async reject(id: string): Promise<{ ok: boolean }> {
      return post(`/api/recovery/candidates/${id}/reject`);
    },
  },
  benchmark: {
    async listReports(): Promise<BenchmarkReport[]> {
      return get("/api/benchmark/reports");
    },
    async run(): Promise<{ started: boolean }> {
      return post("/api/benchmark/run");
    },
  },
  replay: {
    async start(
      templateName: string,
      envKey: string,
      personaName: string,
      headless: boolean,
    ): Promise<{ started: boolean }> {
      return post("/api/replay/start", { templateName, envKey, personaName, headless });
    },
  },
  explore: {
    async start(
      siteKey: string,
      budget: number,
      headless: boolean,
      personaName: string,
    ): Promise<{ started: boolean; runId: string }> {
      return post("/api/explore/start", { siteKey, budget, headless, personaName });
    },
    async listRuns(): Promise<ExploreRun[]> {
      return get("/api/explore/runs");
    },
    async liveState(): Promise<ExploreRun | null> {
      return get("/api/explore/live");
    },
    async ledgerStats(): Promise<FallbackLedgerStats> {
      return get("/api/explore/ledger-stats");
    },
    async vocabProposals(): Promise<VocabProposalSummary> {
      return get("/api/explore/vocab-proposals");
    },
  },
  mission: {
    async list(status?: string): Promise<MissionEntry[]> {
      return get(`/api/missions${status ? `?status=${status}` : ""}`);
    },
    async counts(): Promise<MissionCounts> {
      return get("/api/missions/counts");
    },
    async live(): Promise<MissionLiveState> {
      return get("/api/missions/live");
    },
    async workerStatus(): Promise<{ running: boolean; pid: number | null }> {
      return get("/api/missions/worker-status");
    },
    async add(
      siteKey: string,
      persona = "validator",
      budget = 200,
      tags: string[] = [],
      maxRetries = 2,
    ): Promise<{ id: string; siteKey: string; status: string; added: boolean }> {
      return post("/api/missions/add", { siteKey, persona, budget, tags, maxRetries });
    },
    async addBulk(
      siteKeys: string[],
      persona = "validator",
      budget = 200,
      tags: string[] = [],
    ): Promise<{ added: number; total: number }> {
      return post("/api/missions/add-bulk", { siteKeys, persona, budget, tags });
    },
    async run(opts: {
      hours?: number;
      maxSites?: number;
      headless?: boolean;
      persona?: string;
    }): Promise<{ started: boolean; pid: number }> {
      return post("/api/missions/run", opts);
    },
    async stop(): Promise<{ stopped: boolean; reason?: string }> {
      return post("/api/missions/stop");
    },
    async resume(siteKey: string): Promise<{ resumed: boolean }> {
      return post(`/api/missions/${encodeURIComponent(siteKey)}/resume`);
    },
    async clear(status: string): Promise<{ removed: number }> {
      return post("/api/missions/clear", { status });
    },
  },
};
