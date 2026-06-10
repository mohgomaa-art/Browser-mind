export type ReplayStatus = 'OK' | 'FAIL' | 'BLOCKED';

export type FailureCategory =
  | 'TARGET_DRIFT'
  | 'NAME_DRIFT'
  | 'PORTAL_FAILURE'
  | 'AMBIGUOUS_TARGET'
  | 'NO_VISIBLE_SIGNAL'
  | 'IDENTITY_EXPIRED'
  | 'IDENTITY_REQUIRES_2FA'
  | 'ENVIRONMENT_FAILURE'
  | 'OTHER';

export interface StepOutcome {
  seq: number;
  outcome:
    | 'RESOLVED_CORRECT'
    | 'RESOLVED_UNJUDGED'
    | 'RESOLVED_INCORRECT'
    | 'NO_VISIBLE_SIGNAL'
    | 'ORPHANED_SEMANTIC_SIGNAL'
    | 'TARGET_CHANGED'
    | 'AMBIGUOUS_TARGET'
    | 'AMBIGUOUS_IDENTITY'
    | 'ENVIRONMENT_FAILURE'
    | 'SKIPPED'
    | 'UNKNOWN';
  targetRole?: string;
  targetName?: string;
}

export interface ReplayReport {
  id: string;
  executionId?: string;
  workflowId: string;
  environmentKey: string;
  status: ReplayStatus;
  resolutionRate: number;
  falsePositiveRate: number | null;
  taskCompletionRate: number | null;
  criticalPath: string[];
  failureCategory?: FailureCategory;
  failureReason?: string;
  totalSteps: number;
  resolvedSteps: number;
  attemptedSteps: number;
  stepOutcomes: StepOutcome[];
  createdAt: string;
}
