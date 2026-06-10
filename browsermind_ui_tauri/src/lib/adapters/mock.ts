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
import {
  SEED_ANALYTICS,
  SEED_ENVIRONMENTS,
  SEED_EXECUTIONS,
  SEED_IDENTITIES,
  SEED_LEDGER,
  SEED_MEMORY,
  SEED_PERSONAS,
  SEED_PRINCIPALS,
  SEED_REPLAYS,
  SEED_TASKS,
  SEED_WORKFLOWS,
} from "./seed";

function sleep(): Promise<void> {
  const ms = 80 + Math.random() * 170;
  return new Promise((r) => setTimeout(r, ms));
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export interface SystemStatus {
  activeSessions: number;
  backgroundJobs: number;
  memoryMb: number;
  replayStatus: "idle" | "recording" | "replaying";
}

export const mockAdapter = {
  principals: {
    async list(): Promise<Principal[]> {
      await sleep();
      return clone(SEED_PRINCIPALS);
    },
  },
  personas: {
    async list(): Promise<Persona[]> {
      await sleep();
      return clone(SEED_PERSONAS);
    },
    async byId(id: string): Promise<Persona | null> {
      await sleep();
      const found = SEED_PERSONAS.find((p) => p.id === id);
      return found ? clone(found) : null;
    },
  },
  identities: {
    async list(personaId?: string): Promise<Identity[]> {
      await sleep();
      const all = personaId
        ? SEED_IDENTITIES.filter((i) => i.personaId === personaId)
        : SEED_IDENTITIES;
      return clone(all);
    },
    async byId(id: string): Promise<Identity | null> {
      await sleep();
      const found = SEED_IDENTITIES.find((i) => i.id === id);
      return found ? clone(found) : null;
    },
  },
  environments: {
    async list(): Promise<Environment[]> {
      await sleep();
      return clone(SEED_ENVIRONMENTS);
    },
    async byKey(key: string): Promise<Environment | null> {
      await sleep();
      const found = SEED_ENVIRONMENTS.find((e) => e.key === key);
      return found ? clone(found) : null;
    },
  },
  tasks: {
    async list(filter?: { state?: TaskState; personaId?: string }): Promise<Task[]> {
      await sleep();
      let items = SEED_TASKS;
      if (filter?.state) items = items.filter((t) => t.state === filter.state);
      if (filter?.personaId)
        items = items.filter((t) => t.personaId === filter.personaId);
      return clone(items);
    },
    async byId(id: string): Promise<Task | null> {
      await sleep();
      const found = SEED_TASKS.find((t) => t.id === id);
      return found ? clone(found) : null;
    },
  },
  executions: {
    async list(filter?: {
      taskId?: string;
      state?: ExecutionState;
    }): Promise<Execution[]> {
      await sleep();
      let items = SEED_EXECUTIONS;
      if (filter?.taskId) items = items.filter((e) => e.taskId === filter.taskId);
      if (filter?.state) items = items.filter((e) => e.state === filter.state);
      return clone(items);
    },
    async byId(id: string): Promise<Execution | null> {
      await sleep();
      const found = SEED_EXECUTIONS.find((e) => e.id === id);
      return found ? clone(found) : null;
    },
    async act(
      id: string,
      action: "pause" | "resume" | "retry" | "cancel",
    ): Promise<void> {
      await sleep();
      // eslint-disable-next-line no-console
      console.log(`[mock] execution.act(${id}, ${action})`);
    },
  },
  workflows: {
    async list(): Promise<WorkflowTemplate[]> {
      await sleep();
      return clone(SEED_WORKFLOWS);
    },
    async byId(id: string): Promise<WorkflowTemplate | null> {
      await sleep();
      const found = SEED_WORKFLOWS.find((w) => w.id === id);
      return found ? clone(found) : null;
    },
  },
  replays: {
    async list(filter?: {
      workflowId?: string;
      environmentKey?: string;
    }): Promise<ReplayReport[]> {
      await sleep();
      let items = SEED_REPLAYS;
      if (filter?.workflowId)
        items = items.filter((r) => r.workflowId === filter.workflowId);
      if (filter?.environmentKey)
        items = items.filter((r) => r.environmentKey === filter.environmentKey);
      return clone(items);
    },
    async byId(id: string): Promise<ReplayReport | null> {
      await sleep();
      const found = SEED_REPLAYS.find((r) => r.id === id);
      return found ? clone(found) : null;
    },
  },
  ledger: {
    async list(filter?: {
      kind?: LedgerKind;
      since?: string;
      entityType?: string;
    }): Promise<LedgerEvent[]> {
      await sleep();
      let items = SEED_LEDGER;
      if (filter?.kind) items = items.filter((e) => e.kind === filter.kind);
      if (filter?.entityType)
        items = items.filter((e) => e.entityType === filter.entityType);
      if (filter?.since) {
        const sinceMs = new Date(filter.since).getTime();
        items = items.filter((e) => new Date(e.timestamp).getTime() >= sinceMs);
      }
      return clone(items);
    },
  },
  memory: {
    async list(type?: MemoryType): Promise<MemoryEntry[]> {
      await sleep();
      const items = type ? SEED_MEMORY.filter((m) => m.type === type) : SEED_MEMORY;
      return clone(items);
    },
  },
  analytics: {
    async metrics(): Promise<AnalyticsMetrics> {
      await sleep();
      return clone(SEED_ANALYTICS);
    },
  },
  system: {
    async status(): Promise<SystemStatus> {
      await sleep();
      return {
        activeSessions: 2,
        backgroundJobs: 1,
        memoryMb: 312 + Math.floor(Math.random() * 24),
        replayStatus: "idle",
      };
    },
  },
  training: {
    async status() {
      await sleep();
      return {
        episodeCount: 381,
        checkpointLoaded: true,
        checkpointPath: "bc_v2_checkpoint.pt",
        actionAcc: 1.0,
        valLoss: 0.0052,
        lastTrainedAt: "2026-06-07T02:00:00Z",
      };
    },
    async startTrain() { await sleep(); return { started: true }; },
    async startSelfTrain() { await sleep(); return { started: true }; },
  },
  recovery: {
    async listCandidates() {
      await sleep();
      return [];
    },
    async approve(_id: string) { await sleep(); return { ok: true }; },
    async reject(_id: string) { await sleep(); return { ok: true }; },
  },
  benchmark: {
    async listReports() {
      await sleep();
      return [
        {
          filename: "benchmark_20260607.json",
          timestamp: "2026-06-07T02:00:00",
          aggregateSuccessRate: 0.25,
          workflowCount: 4,
          runsPerWorkflow: 5,
          workflows: [
            { name: "saucedemo_login", successRate: 1.0, description: "SauceDemo login" },
            { name: "saucedemo_add_to_cart", successRate: 0.0, description: "SauceDemo add to cart" },
            { name: "demoqa_form_fill", successRate: 0.0, description: "DemoQA form" },
            { name: "the_internet_login", successRate: 0.0, description: "The Internet login" },
          ],
        },
      ];
    },
    async run() { await sleep(); return { started: true }; },
  },
  replay: {
    async start(_templateName: string, _envKey: string, _personaName: string, _headless: boolean) {
      await sleep();
      return { started: true };
    },
  },
  explore: {
    async start(_siteKey: string, _budget: number, _headless: boolean, _personaName: string) {
      await sleep();
      return { started: true, runId: "mock-run-1" };
    },
    async listRuns() {
      await sleep();
      return [];
    },
    async liveState() {
      await sleep();
      return null;
    },
    async ledgerStats() {
      await sleep();
      return { uniqueFragments: 0, totalObservations: 0, multiSiteFragments: 0, topFragments: [] };
    },
    async vocabProposals() {
      await sleep();
      return { total: 0, byStatus: {} };
    },
  },
  mission: {
    async list(_status?: string): Promise<MissionEntry[]> {
      await sleep();
      return [
        {
          id: "mock-1",
          site_key: "github",
          persona: "validator",
          budget: 200,
          status: "done",
          attempts: 1,
          max_retries: 2,
          priority: 0,
          tags: ["dev"],
          added_at: Date.now() / 1000 - 3600,
          last_run_ts: Date.now() / 1000 - 1800,
          last_error: null,
          last_steps: 45,
          last_hypotheses: 7,
          last_experiences: [],
          last_duration: 34.2,
          run_history: [
            { ts: Date.now() / 1000 - 1800, status: "done", steps: 45, hypotheses: 7, duration: 34.2, quality_score: 0.82 },
          ],
        },
        {
          id: "mock-2",
          site_key: "reddit",
          persona: "validator",
          budget: 200,
          status: "paused",
          attempts: 1,
          max_retries: 2,
          priority: 0,
          tags: ["social"],
          added_at: Date.now() / 1000 - 7200,
          last_run_ts: Date.now() / 1000 - 900,
          last_error: "bot_wall: cloudflare challenge",
          last_steps: 3,
          last_hypotheses: 0,
          last_experiences: [],
          last_duration: 5.1,
          run_history: [
            { ts: Date.now() / 1000 - 900, status: "paused", steps: 3, hypotheses: 0, duration: 5.1, quality_score: 0 },
          ],
        },
        {
          id: "mock-3",
          site_key: "linkedin",
          persona: "validator",
          budget: 200,
          status: "pending",
          attempts: 0,
          max_retries: 2,
          priority: 1,
          tags: ["social", "auth"],
          added_at: Date.now() / 1000 - 600,
          last_run_ts: null,
          last_error: null,
          last_steps: null,
          last_hypotheses: null,
          last_experiences: null,
          last_duration: null,
          run_history: [],
        },
      ];
    },
    async counts(): Promise<MissionCounts> {
      await sleep();
      return { pending: 3, running: 1, done: 12, failed: 2, paused: 1, skipped: 0 };
    },
    async live(): Promise<MissionLiveState> {
      await sleep();
      return {
        isWorkerRunning: true,
        currentSite: "twitter",
        currentAction: "fill",
        currentRole: "searchbox",
        currentName: "Search Twitter",
        stepSeq: 12,
        stepsSoFar: 12,
        successSoFar: 9,
        failedSoFar: 3,
        totalSteps: 200,
        isPaused: false,
        lastUpdateTs: new Date().toISOString(),
        queueCounts: { pending: 3, running: 1, done: 12, failed: 2, paused: 1, skipped: 0 },
        needsHuman: true,
        pausedSites: ["reddit"],
        currentPersona: "validator",
        currentBudget: 200,
      };
    },
    async workerStatus() {
      await sleep();
      return { running: true, pid: 12345 };
    },
    async add(_siteKey: string) {
      await sleep();
      return { id: "mock-new", siteKey: _siteKey, status: "pending", added: true };
    },
    async addBulk(siteKeys: string[]) {
      await sleep();
      return { added: siteKeys.length, total: siteKeys.length };
    },
    async run(_opts: object) {
      await sleep();
      return { started: true, pid: 9999 };
    },
    async stop() {
      await sleep();
      return { stopped: true };
    },
    async resume(_siteKey: string) {
      await sleep();
      return { resumed: true };
    },
    async clear(_status: string) {
      await sleep();
      return { removed: 0 };
    },
  },
};
