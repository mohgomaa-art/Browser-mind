export type ExecutionState =
  | 'pending'
  | 'running'
  | 'paused'
  | 'waiting'
  | 'failed'
  | 'completed'
  | 'cancelled';

export interface ExecutionEvent {
  id: string;
  timestamp: string;
  kind:
    | 'navigate'
    | 'click'
    | 'fill'
    | 'extract'
    | 'verify'
    | 'pause'
    | 'resume'
    | 'fail'
    | 'snapshot';
  summary: string;
  detail?: string;
  resolverStrategy?: string;
}

export interface Snapshot {
  id: string;
  sequence: number;
  kind: 'pre_step' | 'post_step' | 'recovery' | 'manual';
  timestamp: string;
  evidenceUri?: string;
}

export interface Checkpoint {
  id: string;
  label: string;
  timestamp: string;
  sequence: number;
}

export interface RecoveryEvent {
  id: string;
  timestamp: string;
  reason: string;
  outcome: 'recovered' | 'failed';
}

export interface Execution {
  id: string;
  taskId: string;
  workflowId?: string;
  state: ExecutionState;
  startedAt: string;
  endedAt?: string;
  retryCount: number;
  currentStepSeq?: number;
  snapshots: Snapshot[];
  checkpoints: Checkpoint[];
  recoveryHistory: RecoveryEvent[];
  events: ExecutionEvent[];
}
