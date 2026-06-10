export type MissionStatus =
  | "pending"
  | "running"
  | "done"
  | "failed"
  | "paused"
  | "skipped";

export interface MissionEntry {
  id: string;
  site_key: string;
  persona: string;
  budget: number;
  status: MissionStatus;
  attempts: number;
  max_retries: number;
  priority: number;
  tags: string[];
  added_at: number;
  last_run_ts: number | null;
  last_error: string | null;
  last_steps: number | null;
  last_hypotheses: number | null;
  last_experiences: string[] | null;
  last_duration: number | null;
  run_history?: Array<{
    ts: number;
    status: string;
    steps: number;
    hypotheses: number;
    duration: number;
    quality_score?: number;
  }>;
}

export interface MissionCounts {
  pending: number;
  running: number;
  done: number;
  failed: number;
  paused: number;
  skipped: number;
}

export interface MissionLiveState {
  isWorkerRunning: boolean;
  currentSite: string | null;
  currentAction: string | null;
  currentRole: string | null;
  currentName: string | null;
  stepSeq: number;
  stepsSoFar: number;
  successSoFar: number;
  failedSoFar: number;
  totalSteps: number;
  isPaused: boolean;
  lastUpdateTs: string | null;
  queueCounts: MissionCounts;
  needsHuman: boolean;
  pausedSites: string[];
  currentPersona: string | null;
  currentBudget: number | null;
}
