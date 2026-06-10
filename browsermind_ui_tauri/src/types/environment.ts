export type EnvironmentStatus = 'connected' | 'needs_login' | 'error' | 'disconnected';
export type ReplayCompatibility = 'full' | 'partial' | 'none';

export interface Environment {
  key: string;
  label: string;
  family: string;
  startUrl: string;
  status: EnvironmentStatus;
  cookieCount?: number;
  storageStateBytes?: number;
  lastLoginAt?: string;
  replayCompatibility: ReplayCompatibility;
  iconHint?: string;
}
