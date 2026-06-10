export type TaskState =
  | 'created'
  | 'running'
  | 'paused'
  | 'waiting'
  | 'blocked'
  | 'failed'
  | 'completed';

export interface TaskProgress {
  current: number;
  total: number;
}

export interface Task {
  id: string;
  personaId: string;
  environmentKey?: string;
  goal: string;
  state: TaskState;
  progress: TaskProgress;
  missingResources: string[];
  nextAction?: string;
  lastEventAt?: string;
  createdAt: string;
  updatedAt: string;
}
