import type { FailureCategory } from './replay';

export interface FailureSlice {
  category: FailureCategory;
  share: number;
}

export interface AnalyticsMetrics {
  replayResolutionRate: number;
  falsePositiveRate: number;
  taskCompletionRate: number;
  identityDrift: number;
  replayCeiling: number;
  environmentStability: number;
  failureOntology: FailureSlice[];
  trend: { date: string; resolutionRate: number; fpr: number }[];
}
